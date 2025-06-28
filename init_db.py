#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
init_db.py · unified
====================
初始化（或升級）整顆 SQLite：

  • function_runtime  — 函式執行時間 + 系統資源 + 能耗 + 並行人數
  • plan              — 行程 / 推薦結果
  • locust_stats      — Locust 壓力測試彙總 (Avg / P95 / RPS / Failures)
  • v_fn_5m_avg       — ↑ function_runtime 每 5 分鐘彙整檢視
  • v_ls_5m_rate      — ↑ locust_stats   每 5 分鐘彙整檢視

執行一次即可；之後若新增欄位或調整 view，重跑即可自動補 / 取代。
"""
from __future__ import annotations
import os
import sqlite3
import pathlib

# ------------------------------------------------------------------------------
# 0) 讀取 DB 路徑（優先 .env / config；否則預設 ./data/metrics.db）
# ------------------------------------------------------------------------------
try:
    from config import D1_BINDING as _DB_PATH
except Exception:
    _DB_PATH = os.getenv("D1_BINDING", "./data/metrics.db")

DB_PATH = pathlib.Path(_DB_PATH).expanduser().resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)   # 確保資料夾存在

# ------------------------------------------------------------------------------
# 1) 建立 / 升級資料表
# ------------------------------------------------------------------------------
with sqlite3.connect(DB_PATH) as con:
    cur = con.cursor()

    # ---------- 1. function_runtime ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS function_runtime(
          ts               INTEGER,   -- epoch (ms)
          fn               TEXT,      -- function name
          duration_ms      REAL,      -- latency (ms)
          cpu_percent      REAL,      -- CPU usage (%)
          mem_percent      REAL,      -- Memory usage (%)
          energy_joule     REAL,      -- energy (J)
          concurrent_users INTEGER    -- # users running this fn
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fn_ts ON function_runtime(fn, ts)")

    # 動態補欄位（舊 DB → 新欄位）
    for col, typ in [
        ("cpu_percent",      "REAL"),
        ("mem_percent",      "REAL"),
        ("energy_joule",     "REAL"),
        ("concurrent_users", "INTEGER"),
    ]:
        try:
            cur.execute(f"ALTER TABLE function_runtime ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass   # 欄位已存在

    # ---------- 2. plan ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS plan(
          no           TEXT,
          time         TEXT,
          poi          TEXT,
          user_id      TEXT,
          place        TEXT,
          latitude     REAL,
          longitude    REAL,
          bplu_id      TEXT,
          age          INTEGER,
          gender       INTEGER,
          weather      TEXT,
          place_id     TEXT,
          crowd        INTEGER,
          crowd_rank   INTEGER
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_plan_user ON plan(user_id)")

    # ---------- 3. locust_stats ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS locust_stats(
          ts        INTEGER,  -- epoch (ms) at test stop
          endpoint  TEXT,     -- e.g. "POST / location"
          method    TEXT,     -- HTTP method
          avg_ms    REAL,
          p95_ms    REAL,
          rps       REAL,
          failures  INTEGER,
          PRIMARY KEY (ts, endpoint, method)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_locust_ts ON locust_stats(ts)")

    # ------------------------------------------------------------------------------
    # 2) 建立 / 更新 VIEW  (需 SQLite 3.25+ 以支援 Window Function)
    # ------------------------------------------------------------------------------
    cur.executescript("""
    /*  ────────────── function_runtime 每 5 分鐘彙整 ────────────── */
    DROP VIEW IF EXISTS v_fn_5m_avg;
    CREATE VIEW v_fn_5m_avg AS
    WITH fr AS (
        SELECT
            fn,
            (ts / 300000) * 300000        AS bucket_ms,        -- 5 min bin
            duration_ms,
            cpu_percent,
            mem_percent,
            concurrent_users
        FROM function_runtime
    ),
    stats AS (
        SELECT
            fn,
            bucket_ms,
            COUNT(*)                                   AS reqs,
            AVG(duration_ms)                           AS avg_duration_ms,
            AVG(cpu_percent)                           AS avg_cpu,
            AVG(mem_percent)                           AS avg_mem,
            AVG(concurrent_users)                      AS avg_users,
            /* p95 – Row_Number 排序法 */
            duration_ms                                AS dur_ms_for_p95,
            ROW_NUMBER() OVER (PARTITION BY fn, bucket_ms
                               ORDER BY duration_ms)   AS rn,
            COUNT(*)  OVER (PARTITION BY fn, bucket_ms) AS cnt
        FROM fr
    )
    SELECT
        fn,
        bucket_ms,
        datetime(bucket_ms/1000,'unixepoch')           AS bucket_time,
        reqs,
        avg_duration_ms,
        /* 0.95*(n-1)+1 的整數位置；與 rn 相符時即 p95 */
        avg_cpu,
        avg_mem,
        avg_users,
        dur_ms_for_p95          AS p95_dur_ms
    FROM stats
    WHERE rn = CAST(0.95*(cnt-1)+1 AS INTEGER);

    /*  ────────────── locust_stats 每 5 分鐘彙整 ────────────── */
    DROP VIEW IF EXISTS v_ls_5m_rate;
    CREATE VIEW v_ls_5m_rate AS
    WITH ls AS (
        SELECT
            (ts / 300000) * 300000                     AS bucket_ms,
            endpoint,
            method,
            avg_ms,
            p95_ms,
            rps,
            failures
        FROM locust_stats
    ),
    agg AS (
        SELECT
            bucket_ms,
            endpoint,
            method,
            AVG(avg_ms)      AS avg_ms,
            AVG(p95_ms)      AS p95_ms,
            AVG(rps)         AS avg_rps,
            SUM(failures)    AS total_failures,
            100.0 * SUM(failures) /
                NULLIF(SUM(rps)*300, 0)  AS error_rate_pct   -- rps*300s ≈ reqs
        FROM ls
        GROUP BY bucket_ms, endpoint, method
    )
    SELECT
        bucket_ms,
        datetime(bucket_ms/1000,'unixepoch')           AS bucket_time,
        endpoint,
        method,
        avg_ms,
        p95_ms,
        avg_rps,
        total_failures,
        error_rate_pct
    FROM agg;
    """)

    con.commit()

print(f"✅  DB 初始化 / 升級完成 → {DB_PATH}")
