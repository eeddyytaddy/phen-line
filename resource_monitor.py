import os
import sqlite3
import threading
import time
import psutil
from datetime import datetime

# Optional energy measurement using pyRAPL
try:
    import pyRAPL
    pyRAPL.setup()  # initialize pyRAPL
    RAPL_AVAILABLE = True
except ImportError:
    print("⚠️ pyRAPL 初始化失敗：No module named 'pyRAPL'")
    RAPL_AVAILABLE = False

# Load SQLite DB path from environment or use default
DB_PATH = os.environ.get("SQLITE_DB_PATH", "resource.db")
# Ensure the directory for the DB exists (if a directory is specified)
dir_path = os.path.dirname(DB_PATH)
if dir_path:
    os.makedirs(dir_path, exist_ok=True)


def _db_conn():
    """
    Create a SQLite connection with WAL journal mode.
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():
    """
    Create the resource_usage table if it doesn't exist.
    """
    with _db_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS resource_usage (
                ts INTEGER PRIMARY KEY,
                cpu_percent REAL,
                mem_available INTEGER,
                mem_used INTEGER,
                rapl_pkg_joules REAL,
                rapl_dram_joules REAL
            )
            """
        )
        conn.commit()


def record_usage(interval=1):
    """
    Periodically record CPU, memory, and optional energy usage to the database.
    """
    init_db()
    last_pkg = None
    last_dram = None
    while True:
        ts = int(time.time())
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        pkg_joules = None
        dram_joules = None
        if RAPL_AVAILABLE:
            meter = pyRAPL.Measurement('resource')
            meter.begin()
            # You can insert a workload here if desired
            meter.end()
            result = meter.result
            pkg_joules = result.pkg[0]
            dram_joules = result.dram[0]
        # Insert a record
        with _db_conn() as conn:
            conn.execute(
                """
                INSERT INTO resource_usage (ts, cpu_percent, mem_available, mem_used, rapl_pkg_joules, rapl_dram_joules)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ts, cpu, mem.available, mem.used, pkg_joules, dram_joules)
            )
            conn.commit()
        time.sleep(interval)


def start_monitor(interval=1):
    """
    Start the resource usage monitoring in a background thread.
    """
    monitor_thread = threading.Thread(target=record_usage, args=(interval,), daemon=True)
    monitor_thread.start()


if __name__ == "__main__":
    # Start monitoring at 1-second intervals by default
    monitor_interval = float(os.environ.get("MONITOR_INTERVAL", 1))
    start_monitor(monitor_interval)
    print(f"Resource monitor started with interval={monitor_interval}s. Database: {DB_PATH}")
    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Resource monitoring stopped by user.")
