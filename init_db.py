# init_db.py
import sqlite3
import os
from config import D1_BINDING

# 如果 D1_BINDING 包含目录，就先建目录
db_dir = os.path.dirname(D1_BINDING)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir)

with sqlite3.connect(D1_BINDING) as con:
    cur = con.cursor()

    # 1) 建立 function_runtime
    cur.execute("""
    CREATE TABLE IF NOT EXISTS function_runtime(
      ts          INTEGER,    -- UNIX epoch 秒
      fn          TEXT,       -- 函式名稱
      duration_ms REAL        -- 執行時間（毫秒）
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fn_ts ON function_runtime(fn, ts)")

    # 2) 建立 plan 表（如果不存在），并用 try/except 防止重复或列不符错误
    try:
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
        )""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_plan_user ON plan(user_id)")
    except sqlite3.OperationalError as e:
        # 如果已经存在不吻合的 schema，就打印警告但继续
        print(f"⚠️ plan 表初始化时发生错误，已跳过：{e}")

    con.commit()

print(f"✅ 資料表已初始化：function_runtime、plan → {D1_BINDING}")
