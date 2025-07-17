# shared.py
import threading
# ─── 忽略 fork 之後的 threading._after_fork 呼叫，避免 gevent._gevent_cevent.Event 不能呼叫的錯 ───
threading._after_fork = lambda: None

import sqlite3
import json
import os
from collections.abc import MutableMapping
from typing import Any, Callable

# 用於保護 SQLite 寫入的鎖
_lock = threading.Lock()

class SQLiteMap(MutableMapping):
    """
    SQLite-backed dict-like mapping.
    key: str
    value: stored as JSON text
    """
    def __init__(self, db_path: str, table: str, default_factory: Callable[[], Any]):
        # 建立連線並啟用 WAL 模式，提升多進程併發能力
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=5)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.table = table
        self.default_factory = default_factory
        # 建表
        with _lock:
            self.conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table} (
                  key   TEXT PRIMARY KEY,
                  value TEXT NOT NULL
                )
            """)
            self.conn.commit()

    def __getitem__(self, key: str) -> Any:
        cur = self.conn.execute(
            f"SELECT value FROM {self.table} WHERE key = ?", (key,)
        )
        row = cur.fetchone()
        if row:
            return json.loads(row[0])
        # 若不存在，回傳 default 並存入
        val = self.default_factory()
        self[key] = val
        return val

    def __setitem__(self, key: str, value: Any) -> None:
        j = json.dumps(value)
        with _lock:
            self.conn.execute(
                f"INSERT OR REPLACE INTO {self.table} (key, value) VALUES (?, ?)",
                (key, j)
            )
            self.conn.commit()

    def __delitem__(self, key: str) -> None:
        with _lock:
            self.conn.execute(
                f"DELETE FROM {self.table} WHERE key = ?", (key,)
            )
            self.conn.commit()

    def __iter__(self):
        cur = self.conn.execute(f"SELECT key FROM {self.table}")
        for row in cur:
            yield row[0]

    def __len__(self) -> int:
        cur = self.conn.execute(f"SELECT COUNT(*) FROM {self.table}")
        return cur.fetchone()[0]

# 資料庫檔案（建議放在專案根目錄或可寫目錄）
_db_file = os.path.join(os.path.dirname(__file__), "user_state.db")

# 將原本的 in-memory dict 全部替換成 SQLiteMap
user_language  = SQLiteMap(_db_file, "user_language",   lambda: "zh")
user_stage     = SQLiteMap(_db_file, "user_stage",      lambda: "ask_language")
user_age       = SQLiteMap(_db_file, "user_age",        lambda: None)
user_gender    = SQLiteMap(_db_file, "user_gender",     lambda: None)
user_trip_days = SQLiteMap(_db_file, "user_trip_days",  lambda: None)
user_preparing = SQLiteMap(_db_file, "user_preparing",  lambda: False)
user_plan_ready= SQLiteMap(_db_file, "user_plan_ready", lambda: False)
user_location  = SQLiteMap(_db_file, "user_location",   lambda: None)
