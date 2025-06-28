# timer.py  —— 量測單支函式的
#  ✦ 執行秒數(duration_ms)
#  ✦ 呼叫當下的 CPU% / Mem%
#  ✦ 同時併發人數(concurrent_users)
#  ✦ 若在 Linux 上，再加總能耗(energy_joule)
# 統一寫進 SQLite:function_runtime，給 routes_metrics.py 繪圖

import functools
import time
import sqlite3
import threading
import platform
from collections import Counter
import psutil                       # 取 CPU / MEM
from config import D1_BINDING

# ──────────────────────────────────────────
# 0. pyRAPL：僅限 Linux；其他平台自動略過
# ──────────────────────────────────────────
USE_PYRAPL = False
try:
    if platform.system() == "Linux":
        import pyRAPL
        pyRAPL.setup()
        USE_PYRAPL = True
    else:
        print("⚠️ pyRAPL 僅支援 Linux，停用能耗量測")
except Exception as e:
    print(f"⚠️ pyRAPL 初始化失敗：{e}")

# ──────────────────────────────────────────
# 1. 資料表欄位自動補  (第一次跑舊 DB 也 OK)
# ──────────────────────────────────────────
with sqlite3.connect(D1_BINDING) as con:
    cur = con.cursor()
    for col in ("cpu_percent", "mem_percent", "energy_joule", "concurrent_users"):
        try:
            cur.execute(f"ALTER TABLE function_runtime ADD COLUMN {col} REAL")
        except sqlite3.OperationalError:
            pass
    con.commit()

# ──────────────────────────────────────────
# 2. 全域狀態
# ──────────────────────────────────────────
_current_option: str | None = None              # e.g. "兩天一夜"
_fn_active      = Counter()                     # 同時併發人數
_lock           = threading.Lock()              # 保護 _fn_active

# 如果有「需要自動加後綴」的函式（行程選項）
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

# ──────────────────────────────────────────
# 3. 主裝飾器
# ──────────────────────────────────────────
def measure_time(fn):
    """在任意函式上加 @measure_time，就會把各項指標寫入 function_runtime"""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        global _current_option

        # 3-1) 若是 run_ml_sort(option, …) → 抓第一個參數當行程天數
        if fn.__name__ == "run_ml_sort" and args:
            _current_option = args[0]

        # 3-2) 統一組出最終 fn_name（加天數後綴）
        base = fn.__name__
        fn_name = f"{base}_{_current_option}" if base in _SUFFIX_FUNCS and _current_option else base

        # 3-3) 併發人數 +1（執行前）
        with _lock:
            _fn_active[fn_name] += 1
            concurr = _fn_active[fn_name]

        # 3-4) 開始計時／能耗
        t0 = time.perf_counter()
        if USE_PYRAPL:
            meter = pyRAPL.Measurement(fn_name)
            meter.begin()

        try:
            return fn(*args, **kwargs)     # ★ 執行原本邏輯 ★
        finally:
            # -------- 執行結束，收集指標 --------
            duration_ms   = round((time.perf_counter() - t0) * 1000, 2)
            cpu_percent   = psutil.cpu_percent(interval=None)
            mem_percent   = psutil.virtual_memory().percent
            energy_joule  = None
            if USE_PYRAPL:
                meter.end()
                energy_joule = (meter.result.pkg + meter.result.dram) / 1e6  # convert µJ → J

            ts = int(time.time() * 1000)

            # -------- 寫入 SQLite --------
            try:
                with sqlite3.connect(D1_BINDING) as con:
                    con.execute(
                        """
                        INSERT INTO function_runtime
                        (ts, fn, duration_ms, cpu_percent, mem_percent,
                         energy_joule, concurrent_users)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (ts, fn_name, duration_ms,
                         cpu_percent, mem_percent,
                         energy_joule, concurr)
                    )
                    con.commit()
            except Exception as e:
                print(f"[measure_time] DB insert failed: {e}")

            # 3-5) 併發人數 -1（收尾）
            with _lock:
                _fn_active[fn_name] -= 1

            # 3-6) run_upload 結束後就把 option 清掉
            if base == "run_upload":
                _current_option = None

            # -------- Console log --------
            extra = f" | CPU={cpu_percent:.1f}% | MEM={mem_percent:.1f}% | N={concurr}"
            if energy_joule is not None:
                extra += f" | energy={energy_joule:.6f}J"
            print(f"[measure_time] {fn_name} | {duration_ms} ms{extra}")

    return wrapper
