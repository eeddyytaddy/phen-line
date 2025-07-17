# shared.py
import sqlite3, json, threading
from collections.abc import MutableMapping
from typing import Any, Callable

# 確保初始化一次，避免多執行緒競爭
_lock = threading.Lock()

class SQLiteMap(MutableMapping):
    def __init__(self, db_path: str, table: str, default_factory: Callable[[], Any]):
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=5)
        # 開啟 WAL 模式，提升併發能力
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.table = table
        self.default_factory = default_factory
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
            f"SELECT value FROM {self.table} WHERE key = ?",
            (key,)
        )
        row = cur.fetchone()
        if row:
            return json.loads(row[0])
        # 如果還沒存過，就回傳預設值，並儲存
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
                f"DELETE FROM {self.table} WHERE key = ?",
                (key,)
            )
            self.conn.commit()

    def __iter__(self):
        cur = self.conn.execute(f"SELECT key FROM {self.table}")
        for row in cur:
            yield row[0]

    def __len__(self) -> int:
        cur = self.conn.execute(f"SELECT COUNT(*) FROM {self.table}")
        return cur.fetchone()[0]


# 把原本的 in-memory dict 全部換成 SQLiteMap
_db_file = "user_state.db"

user_language = SQLiteMap(_db_file, "user_language", lambda: "zh")
user_stage    = SQLiteMap(_db_file, "user_stage",    lambda: "ask_language")
user_age      = SQLiteMap(_db_file, "user_age",      lambda: None)
user_gender   = SQLiteMap(_db_file, "user_gender",   lambda: None)
user_trip_days= SQLiteMap(_db_file, "user_trip_days",lambda: None)
user_preparing= SQLiteMap(_db_file, "user_preparing",lambda: False)
user_plan_ready=SQLiteMap(_db_file, "user_plan_ready",lambda: False)
# 如果還要存 location，預設可以回 None，再在程式裡直接 assign tuple
user_location = SQLiteMap(_db_file, "user_location", lambda: None)
