#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
timer.py ―― 量測單支函式的執行指標
─────────────────────────────────────────────
✔ duration_ms         ：壁鐘時間 (ms)
✔ cpu_percent         ：process 級別 CPU 使用率（已考慮多核，百分比相對於整機）
✔ mem_percent         ：記憶體使用率 (%)
✔ concurrent_users    ：同一函式同時在跑的執行緒／協程數
✔ energy_joule        ：Linux + pyRAPL 時記錄 CPU+DRAM 能耗 (J)
✔ 雙寫：
      1) SQLite  → table=function_runtime
      2) CSV     → env FUNC_RT_CSV, 預設 function_runtime.csv
"""
import csv
import functools
import os
import platform
import sqlite3
import threading
import time
from collections import Counter
from pathlib import Path

import psutil                      # 取 CPU / MEM
from config import D1_BINDING       # SQLite 路徑

# ──────────────────────────────────────────
# 0. pyRAPL：僅限 Linux；其他平台略過
# ──────────────────────────────────────────
USE_PYRAPL = False
try:
    if platform.system() == "Linux":
        import pyRAPL               # type: ignore
        pyRAPL.setup()
        USE_PYRAPL = True
    else:
        print("⚠️ pyRAPL 僅支援 Linux，停用能耗量測")
except Exception as e:              # pragma: no cover
    print(f"⚠️ pyRAPL 初始化失敗：{e}")

# ──────────────────────────────────────────
# 0.5 Process-level CPU 物件 & 熱身
# ──────────────────────────────────────────
PROC       = psutil.Process(os.getpid())
CPU_COUNT  = psutil.cpu_count(logical=True) or 1
# 先熱身，讓下一次 cpu_percent() 有基準
PROC.cpu_percent(interval=None)

# ──────────────────────────────────────────
# 1. 資料表建置 / 欄位自動補
# ──────────────────────────────────────────
with sqlite3.connect(D1_BINDING) as con:
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS function_runtime (
            ts              INTEGER,
            fn              TEXT,
            duration_ms     REAL
        )
        """
    )
    for col in ("cpu_percent", "mem_percent",
                "energy_joule", "concurrent_users"):
        try:
            cur.execute(f"ALTER TABLE function_runtime ADD COLUMN {col} REAL")
        except sqlite3.OperationalError:
            pass
    con.commit()

# ──────────────────────────────────────────
# 2. CSV 設定
# ──────────────────────────────────────────
CSV_PATH   = Path(os.getenv("FUNC_RT_CSV", "function_runtime.csv"))
_CSV_LOCK  = threading.Lock()
_CSV_HDR   = ["ts", "fn", "duration_ms",
              "cpu_percent", "mem_percent",
              "energy_joule", "concurrent_users"]

if not CSV_PATH.exists():
    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerow(_CSV_HDR)

# ──────────────────────────────────────────
# 3. 全域狀態
# ──────────────────────────────────────────
_current_option: str | None = None              # 行程 ± 天數
_fn_active      = Counter()                     # 併發計數
_lock           = threading.Lock()              # 保護 _fn_active

_SUFFIX_FUNCS = {
    "process_travel_planning",
    "update_plan_csv_with_populartimes",
    "get_current_popularity",
    "run_ml_sort",
    "run_filter",
    "run_ranking",
    "run_upload",
}

# ──────────────────────────────────────────
# 4. 主裝飾器
# ──────────────────────────────────────────
def measure_time(fn):
    """在任意函式上加 @measure_time，即自動紀錄指標到 SQLite + CSV"""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        global _current_option

        # 4-1) 若為 run_ml_sort(option, …) → 抓第一參數作行程天數
        if fn.__name__ == "run_ml_sort" and args:
            _current_option = args[0]

        # 4-2) 組 fn 名稱（加後綴）
        base    = fn.__name__
        fn_name = f"{base}_{_current_option}" \
            if base in _SUFFIX_FUNCS and _current_option else base

        # 4-3) 併發 +1
        with _lock:
            _fn_active[fn_name] += 1
            concurr = _fn_active[fn_name]

        # 4-4) 開始計時 / 能耗
        t0 = time.perf_counter()
        if USE_PYRAPL:
            meter = pyRAPL.Measurement(fn_name)   # type: ignore
            meter.begin()

        try:
            return fn(*args, **kwargs)            # ★ 原函式 ★
        finally:
            # 4-5) 收集指標
            duration_ms  = round((time.perf_counter() - t0) * 1000, 2)

            # process-level CPU%，並 clamp 0~100
            raw_cpu      = PROC.cpu_percent(interval=None)
            cpu_percent  = max(0.0, min(raw_cpu / CPU_COUNT, 100.0))

            mem_percent  = psutil.virtual_memory().percent

            energy_joule = None
            if USE_PYRAPL:
                meter.end()                       # type: ignore
                energy_joule = (meter.result.pkg + meter.result.dram) / 1e6  # µJ→J

            ts = int(time.time() * 1000)

            # 4-6) 寫 SQLite
            try:
                with sqlite3.connect(D1_BINDING) as con:
                    con.execute(
                        """
                        INSERT INTO function_runtime
                        (ts, fn, duration_ms,
                         cpu_percent, mem_percent,
                         energy_joule, concurrent_users)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (ts, fn_name, duration_ms,
                         cpu_percent, mem_percent,
                         energy_joule, concurr)
                    )
                    con.commit()
            except Exception as e:                # pragma: no cover
                print(f"[measure_time] DB insert failed: {e}")

            # 4-7) 寫 CSV（thread-safe）
            try:
                with _CSV_LOCK:
                    with CSV_PATH.open("a", newline="", encoding="utf-8-sig") as f:
                        w = csv.writer(f)
                        w.writerow([ts, fn_name, duration_ms,
                                    cpu_percent, mem_percent,
                                    energy_joule, concurr])
            except Exception as e:                # pragma: no cover
                print(f"[measure_time] CSV write failed: {e}")

            # 4-8) 併發 -1
            with _lock:
                _fn_active[fn_name] -= 1

            # 4-9) run_upload 結束 → 清掉行程天數
            if base == "run_upload":
                _current_option = None

            # 4-10) Console 摘要
            extra = f" | CPU={cpu_percent:.1f}% | MEM={mem_percent:.1f}% | N={concurr}"
            if energy_joule is not None:
                extra += f" | energy={energy_joule:.6f}J"
            print(f"[measure_time] {fn_name} | {duration_ms} ms{extra}")

    return wrapper
