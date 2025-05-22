# report_runtime.py
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime

from config import D1_BINDING

"""
自動產生函式執行時間報表：
  - runtime_trend.png (折線圖)
  - runtime_bar.png   (長條圖)
使用 D1_BINDING 欄位，保證本地或雲端路徑一致
"""

DB_PATH = D1_BINDING

def fetch_data(hours=24):
    """撈取近 N 小時的執行時間紀錄"""
    con = sqlite3.connect(DB_PATH)
    query = f"""
    SELECT ts, fn, duration_ms
    FROM function_runtime
    WHERE ts >= strftime('%s','now','-{hours} hours')
    """
    # 不使用 parse_dates 或 date_parser
    df = pd.read_sql_query(query, con)
    con.close()

    # 將 UNIX 秒數轉為 pandas.Timestamp，並設為索引
    df['ts'] = pd.to_datetime(df['ts'], unit='s')
    df.set_index('ts', inplace=True)
    return df

def plot_trend(df, out_path="runtime_trend.png"):
    """折線圖：時序趨勢"""
    df2 = (
        df
        .pivot(columns='fn', values='duration_ms')
        .resample('1H')
        .mean()
        .ffill()
    )

    plt.figure(figsize=(10,5))
    for fn in df2.columns:
        plt.plot(df2.index, df2[fn], label=fn)
    plt.title(f'Function Runtime Over Time ({len(df2)} hrs)')
    plt.xlabel('Timestamp')
    plt.ylabel('Runtime (ms)')
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()

def plot_bar(df, out_path="runtime_bar.png"):
    """長條圖：平均值比較"""
    df2 = (
        df
        .pivot(columns='fn', values='duration_ms')
        .resample('1H')
        .mean()
    )
    avg = df2.mean()

    plt.figure(figsize=(8,4))
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
        print("⚠️ 近 24 小時無任何記錄，請確認裝飾器是否生效")
    else:
        plot_trend(df)
        plot_bar(df)
        print(f"✅ 圖表已輸出：runtime_trend.png, runtime_bar.png (DB_PATH={DB_PATH})")
