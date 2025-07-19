#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
改版 timer.py —— 精準量測「單次呼叫」的 CPU 與記憶體
========================================================
✅ duration_ms        ：壁鐘時間 (ms)
✅ cpu_seconds        ：此呼叫實際燒掉的 CPU‑seconds (user+sys)
✅ cpu_percent        ：以單核為基準的平均 CPU 使用率 (%)
✅ rss_delta_mb       ：RSS 前後差 (MB)
✅ rss_peak_mb        ：此期間的 RSS 峰值 (MB)
✅ mem_percent        ：系統整體記憶體使用率 (%)  *保留舊欄位供 Dashboard*
✅ concurrent_users   ：同一函式同時在跑的執行緒／協程數
✅ energy_joule       ：Linux + pyRAPL 時紀錄 CPU+DRAM 能耗 (J)

指標寫入兩處：
1️⃣ SQLite  → table=function_runtime
2️⃣ CSV     → env FUNC_RT_CSV，預設 function_runtime.csv
"""

from __future__ import annotations

import csv
import functools
import os
import platform
import sqlite3
import threading
import time
from collections import Counter
from pathlib import Path

import psutil                       # 取 CPU / Mem

# 若專案有 config.py，則從那裡取 DB 路徑；否則用預設 ./data/metrics.db
try:
    from config import D1_BINDING  # type: ignore
except Exception:
    D1_BINDING = os.getenv("D1_BINDING", "./data/metrics.db")
    Path(D1_BINDING).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

# ────────────────────────────────────────────────
# 0. pyRAPL：僅 Linux 可用
# ────────────────────────────────────────────────
USE_PYRAPL = False
try:
    if platform.system() == "Linux":
        import pyRAPL  # type: ignore

        pyRAPL.setup()
        USE_PYRAPL = True
    else:
        print("⚠️  pyRAPL 僅支援 Linux，停用能耗量測")
except Exception as exc:  # pragma: no cover
    print(f"⚠️  pyRAPL 初始化失敗：{exc}")

# ────────────────────────────────────────────────
# 1. Process 物件、CPU 核心數 & 熱身
# ────────────────────────────────────────────────
PROC = psutil.Process(os.getpid())
CPU_COUNT = psutil.cpu_count(logical=True) or 1
PROC.cpu_percent(interval=None)  # 熱身一次

# ────────────────────────────────────────────────
# 2. DB schema 自動建表 / 加欄位
# ────────────────────────────────────────────────
_BASE_COLS = [
    ("ts", "INTEGER"),
    ("fn", "TEXT"),
    ("duration_ms", "REAL"),
]
_EXTRA_COLS = [
    ("cpu_seconds", "REAL"),
    ("cpu_percent", "REAL"),
    ("rss_delta_mb", "REAL"),
    ("rss_peak_mb", "REAL"),
    ("mem_percent", "REAL"),
    ("energy_joule", "REAL"),
    ("concurrent_users", "INTEGER"),
]
with sqlite3.connect(D1_BINDING) as _con:
    cur = _con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS function_runtime (
            ts            INTEGER,
            fn            TEXT,
            duration_ms   REAL
        )"""
    )
    for col, typ in _EXTRA_COLS:
        try:
            cur.execute(f"ALTER TABLE function_runtime ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass
    _con.commit()

# ────────────────────────────────────────────────
# 3. CSV 檔案
# ────────────────────────────────────────────────
CSV_PATH = Path(os.getenv("FUNC_RT_CSV", "function_runtime.csv"))
_CSV_LOCK = threading.Lock()
_CSV_HDR = [
    "ts",
    "fn",
    "duration_ms",
    "cpu_seconds",
    "cpu_percent",
    "rss_delta_mb",
    "rss_peak_mb",
    "mem_percent",
    "energy_joule",
    "concurrent_users",
]
if not CSV_PATH.exists():
    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerow(_CSV_HDR)

# ────────────────────────────────────────────────
# 4. 全域併發狀態 & 行程後綴
# ────────────────────────────────────────────────
_current_option: str | None = None  # 行程天數後綴
_fn_active = Counter()  # 併發計數
_lock = threading.Lock()

_SUFFIX_FUNCS = {
    "process_travel_planning",
    "update_plan_csv_with_populartimes",
    "get_current_popularity",
    "csv_up",
    "run_ml_sort",
    "run_filter",
    "run_ranking",
    "run_upload",
    "save_to_sqlite",
}

# ────────────────────────────────────────────────
# 5. 主裝飾器
# ────────────────────────────────────────────────

def measure_time(fn):
    """裝飾任意函式，即可把執行指標寫入 SQLite + CSV"""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        global _current_option

        # 5‑1) 抓行程天數（第一個參數）
        if fn.__name__ == "run_ml_sort" and args:
            _current_option = args[0]

        # 5‑2) 組 fn 名稱（加後綴）
        base = fn.__name__
        fn_name = f"{base}_{_current_option}" if base in _SUFFIX_FUNCS and _current_option else base

        # 5‑3) 併發 +1
        with _lock:
            _fn_active[fn_name] += 1
            concurr = _fn_active[fn_name]

        # 5‑4) 進入前 —— 紀錄 baseline
        t0 = time.perf_counter()
        cpu0_times = PROC.cpu_times()
        cpu0 = cpu0_times.user + cpu0_times.system
        rss0 = PROC.memory_info().rss
        peak_rss = rss0

        if USE_PYRAPL:
            meter = pyRAPL.Measurement(fn_name)  # type: ignore
            meter.begin()

        try:
            return fn(*args, **kwargs)
        finally:
            # 5‑5) 結束 → 蒐集指標
            wall_time = time.perf_counter() - t0
            duration_ms = round(wall_time * 1000, 2)

            cpu1_times = PROC.cpu_times()
            cpu1 = cpu1_times.user + cpu1_times.system
            cpu_seconds = max(0.0, cpu1 - cpu0)
            # 改為以單核為基準計算平均 CPU%（不再除以 CPU_COUNT）
            cpu_percent = min(100.0, cpu_seconds / wall_time * 100.0) if wall_time > 0 else 0.0

            rss1 = PROC.memory_info().rss
            rss_delta_mb = (rss1 - rss0) / 1024 ** 2
            rss_peak_mb = max(peak_rss, rss1) / 1024 ** 2

            mem_percent = psutil.virtual_memory().percent

            energy_joule: float | None = None
            if USE_PYRAPL:
                meter.end()  # type: ignore
                energy_joule = (meter.result.pkg + meter.result.dram) / 1e6

            ts = int(time.time() * 1000)

            # 5‑6) 寫入 SQLite
            try:
                with sqlite3.connect(D1_BINDING) as con:
                    con.execute(
                        """
                        INSERT INTO function_runtime
                        (ts, fn, duration_ms,
                         cpu_seconds, cpu_percent,
                         rss_delta_mb, rss_peak_mb,
                         mem_percent, energy_joule, concurrent_users)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            ts,
                            fn_name,
                            duration_ms,
                            cpu_seconds,
                            cpu_percent,
                            rss_delta_mb,
                            rss_peak_mb,
                            mem_percent,
                            energy_joule,
                            concurr,
                        ),
                    )
                    con.commit()
            except Exception as exc:
                print(f"[measure_time] DB insert failed → {exc}")

            # 5‑7) 寫入 CSV
            try:
                with _CSV_LOCK:
                    with CSV_PATH.open("a", newline="", encoding="utf-8-sig") as f:
                        csv.writer(f).writerow([
                            ts,
                            fn_name,
                            duration_ms,
                            cpu_seconds,
                            cpu_percent,
                            rss_delta_mb,
                            rss_peak_mb,
                            mem_percent,
                            energy_joule,
                            concurr,
                        ])
            except Exception as exc:
                print(f"[measure_time] CSV write failed → {exc}")

            # 5‑8) 併發 -1
            with _lock:
                _fn_active[fn_name] -= 1

            # 5‑9) run_upload 結束 → 清除行程後綴
            if base == "run_upload":
                _current_option = None

            # 5‑10) Console log 摘要
            extra = (
                f" | CPU={cpu_percent:.2f}% ({cpu_seconds:.3f}s)"
                f" | RSSΔ={rss_delta_mb:.2f}MB | Peak={rss_peak_mb:.2f}MB"
                f" | MEM={mem_percent:.1f}% | N={concurr}"
            )
            if energy_joule is not None:
                extra += f" | energy={energy_joule:.6f}J"
            print(f"[measure_time] {fn_name} | {duration_ms} ms{extra}")

    return wrapper
