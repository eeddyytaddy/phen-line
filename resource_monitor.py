#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
resource_monitor.py
────────────────────
• 單一背景執行緒，每 interval 秒記一筆系統資源
• id AUTOINCREMENT ⇒ 不會撞 UNIQUE
• ts 為 epoch-µs (INTEGER)；另加索引
• 用 PRAGMA WAL，允許多讀少寫
• 提供 start() 及 init_app(app, interval) 兩種用法
"""

import os, sqlite3, time, threading, platform
from pathlib import Path
import psutil
import atexit

# ────────────────────────────────────────────────────────────
# 0. (可選) RAPL 能耗量測 – 只有 Linux + pyRAPL 時啟用
RAPL_AVAILABLE = False
if platform.system() == "Linux":
    try:
        import pyRAPL
        pyRAPL.setup()
        RAPL_AVAILABLE = True
    except Exception as e:
        print(f"⚠️  pyRAPL 初始化失敗：{e}，停用能耗量測")

# ────────────────────────────────────────────────────────────
# 1. DB 初始化
DB_PATH = Path(os.getenv("SQLITE_DB_PATH", "runtime.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS resource_usage (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     INTEGER  NOT NULL,            -- epoch 微秒
    cpu    REAL     NOT NULL,
    mem    REAL     NOT NULL,
    rapl_pkg_j REAL,
    rapl_dram_j REAL
);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON resource_usage(ts);
"""

def _open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(_CREATE_SQL)
    return conn

# ────────────────────────────────────────────────────────────
# 2. 背景執行緒
class _Monitor(threading.Thread):
    def __init__(self, interval: int):
        super().__init__(daemon=True, name="resource-monitor")
        self.interval = interval
        self.conn = _open_db()
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            ts = int(time.time() * 1_000_000)          # µs
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            pkg = dram = None
            if RAPL_AVAILABLE:
                try:
                    m = pyRAPL.Measurement("res"); m.begin(); m.end()
                    pkg, dram = m.result.pkg[0], m.result.dram[0]
                except Exception as e:
                    print(f"⚠️  RAPL 量測失敗：{e}")
            self.conn.execute(
                "INSERT INTO resource_usage (ts, cpu, mem, rapl_pkg_j, rapl_dram_j)"
                " VALUES (?,?,?,?,?)",
                (ts, cpu, mem, pkg, dram)
            )
            self.conn.commit()
            time.sleep(self.interval)

    def stop(self):
        self._stop.set()
        self.join(timeout=2)
        self.conn.close()

_monitor: _Monitor | None = None   # 全域唯一實例

def start(interval: int = 5):
    """直接在腳本或 CLI 中呼叫：start(5)"""
    global _monitor
    if _monitor is None:
        _monitor = _Monitor(interval)
        _monitor.start()
        atexit.register(_monitor.stop)
        print(f"[resource_monitor] started interval={interval}s → {DB_PATH}")

def init_app(app, interval: int = 5):
    """對 Flask：在 app 建立後呼叫一次即可"""
    @app.before_first_request
    def _lazy_start():
        start(interval)

# ────────────────────────────────────────────────────────────
# 3. CLI 測試
if __name__ == "__main__":
    interval = float(os.getenv("MONITOR_INTERVAL", 5))
    start(interval)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("🔴 Resource monitoring stopped by user.")
