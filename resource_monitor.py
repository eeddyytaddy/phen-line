#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
resource_monitor.py
────────────────────
持續將系統資源寫入 SQLite，適用 Flask 2.x / 3.x。
"""

from __future__ import annotations
import os, sqlite3, time, threading, platform, atexit
from pathlib import Path
import psutil

# ────────────────────────────────
# 0. (可選) RAPL 能耗量測
RAPL = False
if platform.system() == "Linux":
    try:
        import pyRAPL
        pyRAPL.setup()
        RAPL = True
    except Exception as e:
        print(f"⚠️  pyRAPL 初始化失敗：{e}，停用能耗量測")

# ────────────────────────────────
# 1. SQLite 初始
DB = Path(os.getenv("SQLITE_DB_PATH", "runtime.db"))
DB.parent.mkdir(parents=True, exist_ok=True)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS resource_usage (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  ts      INTEGER  NOT NULL,   -- epoch μs
  cpu     REAL     NOT NULL,   -- % 使用率
  mem     REAL     NOT NULL,   -- % 使用率
  rapl_pkg_j   REAL,
  rapl_dram_j  REAL
);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON resource_usage(ts);
"""

def _open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn

# ────────────────────────────────
# 2. 背景執行緒
class _Worker(threading.Thread):
    def __init__(self, interval: int):
        super().__init__(daemon=True, name="resource-monitor")
        self.interval = interval
        self.db = _open_db()
        self._stop = threading.Event()

    def run(self):
        while not self._stop.is_set():
            ts  = int(time.time() * 1_000_000)          # μs
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            pkg = dram = None
            if RAPL:
                try:
                    m = pyRAPL.Measurement("res"); m.begin(); m.end()
                    pkg, dram = m.result.pkg[0], m.result.dram[0]
                except Exception as e:
                    print(f"⚠️  RAPL 量測失敗：{e}")
            self.db.execute(
                "INSERT INTO resource_usage (ts,cpu,mem,rapl_pkg_j,rapl_dram_j) "
                "VALUES (?,?,?,?,?)",
                (ts, cpu, mem, pkg, dram)
            )
            self.db.commit()
            time.sleep(self.interval)

    def stop(self):
        self._stop.set()
        self.join(timeout=2)
        self.db.close()

_monitor: _Worker | None = None

def start(interval: int = 5):
    """在 CLI 或其他腳本直接呼叫即可啟動監控。"""
    global _monitor
    if _monitor is None:
        _monitor = _Worker(interval)
        _monitor.start()
        atexit.register(_monitor.stop)
        print(f"[resource_monitor] started interval={interval}s → {DB}")

# ────────────────────────────────
# 3. 給 Flask 使用
def init_app(app, interval: int = 5):
    """
    在 app 建立完成後呼叫一次：
        from resource_monitor import init_app
        app = Flask(__name__)
        … 其他設定 …
        init_app(app, interval=5)
    """
    # Flask 2.x 有 before_first_request，Flask 3.x 已拿掉
    if hasattr(app, "before_first_request"):          # Flask ≤ 2.3
        @app.before_first_request
        def _lazy_start():
            start(interval)
    else:                                             # Flask ≥ 3.0
        start(interval)

# ────────────────────────────────
# 4. CLI 測試
if __name__ == "__main__":
    interval = float(os.getenv("MONITOR_INTERVAL", 5))
    start(interval)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("🔴 Resource monitoring stopped by user.")
