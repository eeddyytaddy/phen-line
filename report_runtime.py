# report_runtime.py

import os
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt

# 從環境變數或預設讀取資料庫路徑
DB_PATH = os.environ.get("D1_BINDING") or os.environ.get("SQLITE_DB_PATH", "runtime.db")

# 如果有目錄成分，再建立它
db_dir = os.path.dirname(DB_PATH)
if db_dir:
    os.makedirs(db_dir, exist_ok=True)

def fetch_data(hours: int = 24) -> pd.DataFrame:
    """撈取近 N 小時的執行時間紀錄"""
    con = sqlite3.connect(DB_PATH)
    query = f"""
    SELECT ts, fn, duration_ms
    FROM function_runtime
    WHERE ts >= strftime('%s','now','-{hours} hours')
    """
    df = pd.read_sql_query(query, con)
    con.close()

    # UNIX 秒 → pandas.Timestamp，並設為索引
    df['ts'] = pd.to_datetime(df['ts'], unit='s')
    df.set_index('ts', inplace=True)
    return df

def save_csv(df: pd.DataFrame, out_csv: str) -> None:
    """將 DataFrame 存成 CSV"""
    df.to_csv(out_csv)
    print(f"✅ CSV 已存到：{out_csv}")

def plot_trend(df: pd.DataFrame, out_path: str) -> None:
    """折線圖：每小時平均執行時間趨勢"""
    df2 = (
        df
        .pivot(columns='fn', values='duration_ms')
        .resample('1H')
        .mean()
        .ffill()
    )
    plt.figure(figsize=(10, 5))
    for fn in df2.columns:
        plt.plot(df2.index, df2[fn], label=fn)
    plt.title(f'Function Runtime Over Time ({len(df2)} hrs)')
    plt.xlabel('Timestamp')
    plt.ylabel('Runtime (ms)')
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()

def plot_bar(df: pd.DataFrame, out_path: str) -> None:
    """長條圖：各函式平均執行時間比較"""
    df2 = (
        df
        .pivot(columns='fn', values='duration_ms')
        .resample('1H')
        .mean()
    )
    avg = df2.mean()
    plt.figure(figsize=(8, 4))
    plt.bar(avg.index, avg.values)
    plt.title('Average Function Runtime (Last 24h)')
    plt.xlabel('Function')
    plt.ylabel('Average Runtime (ms)')
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()

if __name__ == "__main__":
    df = fetch_data(hours=24)
    if df.empty:
        print("⚠️ 近 24 小時無任何記錄，請確定 @measure_time 裝飾器已正確套用。")
    else:
        # 範例：存成 CSV、輸出圖檔
        save_csv(df, "runtime.csv")
        plot_trend(df, "runtime_trend.png")
        plot_bar(df,   "runtime_bar.png")
        print("✅ 報表已產生：runtime.csv, runtime_trend.png, runtime_bar.png")
