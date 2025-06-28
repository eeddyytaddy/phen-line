# locust_db.py  ▸ thread-safe WAL sqlite writer（單一檔案版）
from __future__ import annotations
import sqlite3, threading, time
from typing import Any

# -----------------------------------------------------------
# 0. 路徑：一律跟 routes_metrics / init_db 讀同一顆
# -----------------------------------------------------------
from config import LOCUST_DB as DB_PATH     # <── 只改這行

# -----------------------------------------------------------
# 1. 全域連線 (singleton)  + busy_timeout & WAL
# -----------------------------------------------------------
_conn: sqlite3.Connection | None = None
_lock = threading.Lock()

def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        # check_same_thread=False → 多執行緒共用
        _conn = sqlite3.connect(
            DB_PATH,
            check_same_thread=False,
            timeout=30,
            isolation_level=None           # autocommit
        )
        _conn.execute("PRAGMA journal_mode=WAL;")
        _conn.execute("PRAGMA synchronous=NORMAL;")
        _conn.execute("PRAGMA busy_timeout = 5000;")  # 5 s
    return _conn

# -----------------------------------------------------------
# 2. 包一層重試，避免資料庫被鎖
# -----------------------------------------------------------
def _exec(sql: str, params: tuple = (), retry: int = 5) -> None:
    for i in range(retry):
        try:
            with _lock:                        # 全域鎖：單通道寫入
                _get_conn().execute(sql, params)
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and i < retry - 1:
                time.sleep(0.2 * (i + 1))      # 指數退讓
                continue
            raise                             # 其他錯誤直接拋出

# -----------------------------------------------------------
# 3. 對外 API
# -----------------------------------------------------------
def init_table() -> None:
    """確保 `locust_stats` 資料表存在（無論跑幾次都安全）"""
    _exec(
        """CREATE TABLE IF NOT EXISTS locust_stats (
               ts        INTEGER,   -- epoch (ms) at test stop
               endpoint  TEXT,
               method    TEXT,
               avg_ms    REAL,
               p95_ms    REAL,
               rps       REAL,
               failures  INTEGER,
               PRIMARY KEY (ts, endpoint, method)
           )"""
    )

def save_stats(env) -> None:
    """
    在 tests/locustfile.py 的 test_stop hook 裡呼叫：
        events.test_stop.add_listener(save_stats)
    """
    init_table()   # 保險起見，每次寫入前都確保表存在
    for s in env.stats.entries.values():
        _exec(
            "INSERT OR REPLACE INTO locust_stats "
            "VALUES (?,?,?,?,?,?,?)",
            (
                int(time.time() * 1000),
                s.name, s.method,
                s.avg_response_time,
                s.get_response_time_percentile(0.95),
                s.total_rps or 0,
                s.num_failures,
            ),
        )

# -----------------------------------------------------------
# 4. CLI quick-test
# -----------------------------------------------------------
if __name__ == "__main__":
    print("create & insert demo row …")
    init_table()
    _exec(
        "INSERT INTO locust_stats VALUES (?,?,?,?,?,?,?)",
        (int(time.time() * 1000), "GET /demo", "GET", 123.0, 200.0, 1.5, 0)
    )
    for row in _get_conn().execute("SELECT * FROM locust_stats LIMIT 5"):
        print(row)
