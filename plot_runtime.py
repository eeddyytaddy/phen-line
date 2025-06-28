"""
plot_runtime.py
================
從 SQLite 的 function_runtime 撈出最近 N 小時的紀錄，
一次產出 4 張圖：
  1. duration_trend.png      — 不同函式的時間趨勢折線
  2. duration_bar.png        — 24h 平均時間長條
  3. energy_trend.png        — 能耗趨勢折線
  4. energy_bar.png          — 24h 平均能耗長條
"""

import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from config import D1_BINDING


def fetch(hours: int = 24) -> pd.DataFrame:
    """撈近 N 小時資料並回傳 DataFrame (index=Timestamp)"""
    since = int((datetime.utcnow() - timedelta(hours=hours)).timestamp() * 1000)
    sql = """
    SELECT ts, fn, duration_ms, cpu_percent, mem_percent, energy_joule
    FROM   function_runtime
    WHERE  ts >= ?
    """
    df = pd.read_sql(sql, sqlite3.connect(D1_BINDING), params=(since,))
    if df.empty:
        raise SystemExit(f"No data in last {hours}h, abort.")

    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    df.set_index("ts", inplace=True)
    return df


def line_chart(df: pd.DataFrame, col: str, out: str, title: str, ylabel: str):
    """畫折線：fn 當 series、多函式同圖"""
    pivot = (
        df.pivot(columns="fn", values=col)
          .resample("5T")               # 5 分鐘窗
          .mean()
          .ffill()
    )
    plt.figure(figsize=(12, 6))
    for fn in pivot.columns:
        plt.plot(pivot.index, pivot[fn], label=fn)
    plt.title(title)
    plt.ylabel(ylabel)
    plt.xlabel("Timestamp (UTC)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out, dpi=120)
    plt.close()


def bar_chart(df: pd.DataFrame, col: str, out: str, title: str, ylabel: str):
    """畫長條：取每小時平均 → 再算 24h 平均"""
    avg = (
        df.pivot(columns="fn", values=col)
          .resample("1H")
          .mean()
          .mean()
          .sort_values(ascending=False)
    )
    plt.figure(figsize=(8, 4))
    plt.bar(avg.index, avg.values)
    plt.title(title)
    plt.ylabel(ylabel)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(out, dpi=120)
    plt.close()


if __name__ == "__main__":
    HOURS = 24          # 近 24 小時
    df = fetch(HOURS)

    # ------ 時間 (ms) ------
    line_chart(df, "duration_ms",
               "duration_trend.png",
               f"Function Runtime Trend (last {HOURS}h)",
               "Duration (ms)")
    bar_chart(df, "duration_ms",
              "duration_bar.png",
              "Avg Function Runtime (last 24h)",
              "Avg Duration (ms)")

    # ------ 能耗 (J)（Linux 才有值） ------
    if df["energy_joule"].notna().any():
        line_chart(df, "energy_joule",
                   "energy_trend.png",
                   f"Function Energy Trend (last {HOURS}h)",
                   "Energy (J)")
        bar_chart(df, "energy_joule",
                  "energy_bar.png",
                  "Avg Function Energy (last 24h)",
                  "Avg Energy (J)")

    print("✅ 圖檔已輸出：duration_*.png, energy_*.png")
