#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
resource_monitor.py
===================
背景執行緒，固定間隔擷取 **整機** CPU / Mem 百分比，
寫入 `function_runtime` 供 dashboard 繪圖。

INSERT 範例
-----------
ts=1719216000123 , fn="__system__", duration_ms=NULL ,
cpu_percent=23.5 , mem_percent=67.2 , concurrent_users=NULL
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import psutil
import sqlite3

# ------------------------------------------------------------------- #
# 0. DB 連線工具 & 表結構確保
# ------------------------------------------------------------------- #
try:
    from config import D1_BINDING as _DB_PATH     # 專案設定
except Exception:
    import os, pathlib
    _DB_PATH = os.getenv("D1_BINDING", "./data/metrics.db")
    pathlib.Path(_DB_PATH).expanduser().resolve().parent.mkdir(
        parents=True, exist_ok=True
    )

def _db_conn() -> sqlite3.Connection:
    """開啟一條具 WAL / busy-timeout 的連線（autocommit 模式）"""
    conn = sqlite3.connect(
        _DB_PATH,
        timeout=5.0,
        isolation_level=None,            # autocommit
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
    )
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")   # ms
    return conn


# -- 建表 & 補欄位（只跑一次） ----------------------------------------
with _db_conn() as _con:
    _con.execute("""
        CREATE TABLE IF NOT EXISTS function_runtime(
          ts               INTEGER,
          fn               TEXT,
          duration_ms      REAL,
          cpu_percent      REAL,
          mem_percent      REAL,
          energy_joule     REAL,
          concurrent_users INTEGER
        );
    """)
    for col, typ in [
        ("cpu_percent",      "REAL"),
        ("mem_percent",      "REAL"),
        ("energy_joule",     "REAL"),
        ("concurrent_users", "INTEGER"),
    ]:
        try:
            _con.execute(f"ALTER TABLE function_runtime ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass
    _con.execute("CREATE INDEX IF NOT EXISTS idx_fn_ts ON function_runtime(fn, ts);" )
# ------------------------------------------------------------------- #


class _MonitorThread(threading.Thread):
    """Daemon thread － 週期性記錄系統 CPU / Mem% 到 SQLite"""

    def __init__(
        self,
        interval: int = 5,
        cb: Optional[Callable[[float, float], None]] = None,
    ):
        super().__init__(daemon=True)
        self.interval = max(1, interval)
        self.cb = cb
        self._stop_evt = threading.Event()

    # -- 執行迴圈 -----------------------------------------------------
    def run(self):
        conn = _db_conn()
        while not self._stop_evt.is_set():
            cpu_pct = psutil.cpu_percent(interval=None)
            mem_pct = psutil.virtual_memory().percent
            ts_ms   = int(time.time() * 1000)

            try:
                conn.execute(
                    """INSERT INTO function_runtime
                       (ts, fn, duration_ms, cpu_percent, mem_percent)
                       VALUES (?,?,?,?,?)""",
                    (ts_ms, "__system__", None, cpu_pct, mem_pct),
                )
            except Exception as exc:        # pragma: no cover
                print(f"[resource_monitor] DB insert failed → {exc}")

            if self.cb:
                try:
                    self.cb(cpu_pct, mem_pct)
                except Exception as exc:    # pragma: no cover
                    print(f"[resource_monitor] callback error → {exc}")

            time.sleep(self.interval)

        conn.close()

    def stop(self):
        self._stop_evt.set()


# ------------------------------------------------------------------- #
# 2. 公共 API
# ------------------------------------------------------------------- #
_monitor: Optional[_MonitorThread] = None


def start_monitor(
    interval: int = 5,
    callback: Optional[Callable[[float, float], None]] = None,
) -> None:
    """
    於背景啟動系統資源監控（僅會啟 1 次）
    :param interval: 取樣秒數；≥1
    :param callback: 取樣後呼叫的函式 (cpu_pct, mem_pct) → None
    """
    global _monitor
    if _monitor is None:
        _monitor = _MonitorThread(interval, callback)
        _monitor.start()
        print(f"[resource_monitor] → started (interval={interval}s)")
    else:
        print("[resource_monitor] → already running")


def stop_monitor() -> None:
    """停止背景監控執行緒"""
    global _monitor
    if _monitor:
        _monitor.stop()
        _monitor = None
        print("[resource_monitor] → stopped")
