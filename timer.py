# timer.py

import functools
import time
import sqlite3

from config import D1_BINDING  # 由 config.py 統一處理資料庫路徑

# 用來暫存當前的行程選項，例如 "兩天一夜"
_current_option = None

def measure_time(fn):
    """
    裝飾器：量測被裝飾函式的執行時間（ms），
    並將結果寫入 function_runtime 資料表（使用 D1_BINDING）。

    - 在 run_ml_sort（讀 CSV + ML 排序）時記錄 option。
    - 所有 run_* 系列函式都會被自動在 fn_name 後加上 _{option}。
    - 只有在 run_upload 執行結束後才清除 option。
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        global _current_option

        # 在 run_ml_sort 時記錄 option（args[0] 應該是 option）
        if fn.__name__ == "run_ml_sort" and args:
            _current_option = args[0]

        start = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            dur_ms = round((time.perf_counter() - start) * 1000, 2)
            ts     = int(time.time())

            base_fn = fn.__name__
            # 需要拼 suffix 的函式清單
            SUFFIX_FUNCS = {
                "process_travel_planning",
                "update_plan_csv_with_populartimes",
                "get_current_popularity",
                "csv_up",
                "run_ml_sort",
                "run_filter",
                "run_ranking",
                "run_upload",
                'save_to_sqlite',
            }
            # 如果是要拼接後綴，且有 _current_option，就加上
            if base_fn in SUFFIX_FUNCS and _current_option:
                fn_name = f"{base_fn}_{_current_option}"
            else:
                fn_name = base_fn

            # DEBUG: 印出量測結果
            print(f"[measure_time] {fn_name} | ts={ts} | duration={dur_ms}ms")

            # 寫入資料庫
            with sqlite3.connect(D1_BINDING) as con:
                con.execute(
                    "INSERT INTO function_runtime(ts, fn, duration_ms) VALUES (?, ?, ?)",
                    (ts, fn_name, dur_ms)
                )

            # 在最末段 run_upload 結束後再清除 option
            if base_fn == "run_upload":
                _current_option = None

    return wrapper
