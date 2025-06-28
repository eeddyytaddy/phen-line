#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
debug_plot_loadtest.py
印資料量 → 畫簡易 Requests/s 走勢
"""

import matplotlib
matplotlib.use("Agg")
import pandas as pd, matplotlib.pyplot as plt
from pathlib import Path

CSV = Path("locust_complete_10_stats_history.csv")
print(f"➡️  讀取 {CSV}")

# ---------- 1. 讀檔 & Timestamp -------------
df_raw = pd.read_csv(CSV)
print(f"📄  CSV rows             : {len(df_raw):,}")

# Timestamp 可能是「毫秒 epoch 整數」或「ISO-8601 字串」
def _parse_ts(x):
    try:
        # 先試整數毫秒
        return pd.to_datetime(int(x), unit="ms", utc=True)
    except Exception:
        # 再試字串
        return pd.to_datetime(x, utc=True, errors="coerce")

df_raw["Timestamp"] = df_raw["Timestamp"].apply(_parse_ts)
good_ts = df_raw["Timestamp"].notna().sum()
print(f"⏱️  Parsed timestamp rows : {good_ts:,}")

# ---------- 2. 只取 Aggregated ----------
df = df_raw[df_raw["Name"] == "Aggregated"].copy()
print(f"🧩  Aggregated rows       : {len(df):,}")

# 把 Requests/s 轉成 float，轉不了 → NaN
df["Requests/s"] = pd.to_numeric(df["Requests/s"], errors="coerce")
df = df[df["Requests/s"].notna()]
print(f"🔢  Numeric Requests/s    : {len(df):,}")

# ---------- 3. 轉相對秒 ----------
df = df.sort_values("Timestamp")
t0 = df["Timestamp"].iloc[0]
df["sec_since_start"] = (df["Timestamp"] - t0).dt.total_seconds()
print(f"⏲️  最早時間 (t0)         : {t0}")
print(f"⏲️  最晚時間 (tN)         : {df['Timestamp'].iloc[-1]}")
print(f"⏲️  測試長度 (秒)         : {df['sec_since_start'].iloc[-1]:.1f}")

# ---------- 4. 每秒圖 ----------
plt.figure(figsize=(10,4))
plt.plot(df["sec_since_start"], df["Requests/s"], lw=2, label="Requests/s")
plt.xlabel("Seconds Since Start")
plt.ylabel("Requests / s")
plt.title("Total Requests per Second")
plt.legend()
plt.tight_layout()
plt.savefig("debug_requests_per_sec.png")
print("✅  輸出 debug_requests_per_sec.png")

# ---------- 5. 每分鐘 resample ----------
df = df.set_index("Timestamp")
per_min = (df["Requests/s"]
           .resample("1min").mean()
           .dropna())
print(f"⏱️  1-min points          : {len(per_min):,}")

if len(per_min) > 1:
    mins = (per_min.index - per_min.index[0]).total_seconds() / 60
    plt.figure(figsize=(10,4))
    plt.plot(mins, per_min.values * 60, lw=2, color="tab:green",
             label="Requests/min")
    plt.xlabel("Minutes Since Start")
    plt.ylabel("Requests / min")
    plt.title("Total Requests per Minute")
    plt.legend()
    plt.tight_layout()
    plt.savefig("debug_requests_per_min.png")
    print("✅  輸出 debug_requests_per_min.png")
else:
    print("⚠️  1-min resample 只有 0 或 1 點，無法畫線")
