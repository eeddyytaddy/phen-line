#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
plot_loadtest_requests_per_sec_10min.py
直接画出前 10 分钟内的 Requests/s（每秒请求数）
"""
import matplotlib
matplotlib.use("Agg")  # 无头环境也能画图

import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

CSV_PATH = Path("locust_complete_stats_history.csv")
print(f"➡️  读取 {CSV_PATH}")

# 1) 读 CSV 并解析 Timestamp 为 UTC datetime
df = pd.read_csv(CSV_PATH)

def _to_dt(x):
    try:
        # 如果是毫秒时间戳
        return pd.to_datetime(int(x), unit="ms", utc=True)
    except:
        # 否则直接尝试解析字符串
        return pd.to_datetime(x, utc=True, errors="coerce")

df["Timestamp"] = df["Timestamp"].apply(_to_dt)

# 2) 只保留 Aggregated 行
df_agg = df[df["Name"] == "Aggregated"].copy()
df_agg["Requests/s"] = pd.to_numeric(df_agg["Requests/s"], errors="coerce")

# 3) 设置 DatetimeIndex
df_agg.set_index("Timestamp", inplace=True)

# 4) 截取前 10 分钟
start = df_agg.index.min()
end   = start + pd.Timedelta(minutes=10)
df_10 = df_agg.loc[start:end]

# 5) 计算横坐标：分钟数，从 0 到 10
x = (df_10.index - start).total_seconds() / 60

# 6) 作图
fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(
    x,
    df_10["Requests/s"],
    color="tab:green",
    linewidth=2,
    label="Requests/s"
)
ax.set_xlabel("Minutes Since Start")
ax.set_ylabel("Requests per Second")
ax.set_xlim(0, 10)
ax.set_ylim(bottom=0)
ax.set_title("Requests/s (First 10 Minutes)")
ax.legend(loc="upper left")
plt.tight_layout()

out_path = "loadtest_requests_per_sec_10min.png"
fig.savefig(out_path)
plt.close(fig)
print(f"✅  输出 {out_path}")
