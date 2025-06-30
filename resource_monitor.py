import os
import sqlite3
import threading
import time
import psutil
import platform

# 僅在 Linux 上啟用能耗量測，其他平台停用
RAPL_AVAILABLE = False
if platform.system() == "Linux":
    try:
        import pyRAPL
        pyRAPL.setup()
        RAPL_AVAILABLE = True
    except Exception as e:
        print(f"⚠️ pyRAPL 初始化失敗：{e}，停用能耗量測")
else:
    print("⚠️ pyRAPL 僅支援 Linux，停用能耗量測")

# 從環境變數載入 SQLite DB 路徑，否則預設為 resource.db
DB_PATH = os.environ.get("SQLITE_DB_PATH", "resource.db")
# 若路徑包含資料夾，則建立之
db_dir = os.path.dirname(DB_PATH)
if db_dir:
    os.makedirs(db_dir, exist_ok=True)


def _db_conn():
    """
    建立 SQLite 連線並使用 WAL 模式
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():
    """
    初始化資源使用表格，如不存在則建立
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
    週期性記錄 CPU%、記憶體與選用的能耗數據至資料庫
    """
    init_db()
    while True:
        ts = int(time.time())
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        pkg_joules = None
        dram_joules = None
        if RAPL_AVAILABLE:
            try:
                meter = pyRAPL.Measurement('resource')
                meter.begin()
                meter.end()
                result = meter.result
                pkg_joules = result.pkg[0]
                dram_joules = result.dram[0]
            except Exception as e:
                print(f"⚠️ 能耗量測失敗：{e}")
        # 將紀錄寫入資料庫
        with _db_conn() as conn:
            conn.execute(
                """
                INSERT INTO resource_usage 
                (ts, cpu_percent, mem_available, mem_used, rapl_pkg_joules, rapl_dram_joules)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ts, cpu, mem.available, mem.used, pkg_joules, dram_joules)
            )
            conn.commit()
        time.sleep(interval)


def start_monitor(interval=1):
    """
    啟動背景執行緒進行資源監控
    """
    monitor = threading.Thread(target=record_usage, args=(interval,), daemon=True)
    monitor.start()
    print(f"✅ Resource monitor started with interval={interval}s. Database: {DB_PATH}")


if __name__ == "__main__":
    # 預設以環境變數或 1 秒為監控頻率
    interval = float(os.environ.get("MONITOR_INTERVAL", 1))
    start_monitor(interval)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("🔴 Resource monitoring stopped by user.")
