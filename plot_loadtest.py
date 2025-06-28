#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
plot_loadtest.py   ─  讀 CSV 畫 4 張圖
────────────────────────────────────────
  1) loadtest_requests_per_min.png          整體每分鐘請求數
  2) loadtest_latency_trend_per_min.png     Avg / Median / P95 Latency
  3) loadtest_commands_requests_per_min.png 各指令每分鐘請求數
  4) loadtest_avg_latency_per_group.png     各分類平均延遲（X 軸直字）
"""
# ───────────────── 0. 全域設定：字體 ───────────────────────
import os, matplotlib, matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from pathlib import Path
import pandas as pd

matplotlib.use("Agg")                     # head-less backend
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = [
    "Source Han Sans TC", "Noto Sans CJK TC", "Noto Sans CJK JP",
    "Noto Sans CJK KR", "Microsoft JhengHei", "PingFang TC",
    "DejaVu Sans",
]

proj_font = Path(__file__).with_suffix("").parent / "fonts" / "SourceHanSansTC-Regular.otf"
if proj_font.exists():
    fm.fontManager.addfont(str(proj_font))
    plt.rcParams["font.sans-serif"].insert(
        0, fm.FontProperties(fname=str(proj_font)).get_name())
    print(f"✅ 使用字體：{proj_font.name}")
else:
    fallback = "Noto Sans CJK TC" if os.getenv("APP_ENV") == "docker" else "Microsoft JhengHei"
    plt.rcParams["font.family"] = fallback
    print(f"ℹ️ 專案字體不存在，使用系統字體：{fallback}")

# ───────────────── 1. 參數與中文映射表 ──────────────────────
CSV_PATH = Path("locust_complete_10_stats_history.csv")

TOKEN_TO_LABEL = {
    # 行程規劃
    "text_2days":  "兩天一夜",
    "text_3days":  "三天兩夜",
    "text_4days":  "四天三夜",
    "text_5days":  "五天四夜",
    # 景點推薦
    "text_recommend":        "一般景點推薦",
    "text_sustain":          "永續觀光",
    "general_places":        "一般景點推薦",
    "sustainable_places":    "永續觀光",
    "text_crowd":            "人潮熱點",
    # 附近搜尋（4 合 1）
    "text_restaurants":      "附近搜尋",
    "text_parking":          "附近搜尋",
    "text_scenic_spots":     "附近搜尋",
    "text_accommodation":    "附近搜尋",
    # 其他
    "text_rental":           "租車",
    "lang_zh":               "語言",
    "age_25":                "年齡",
    "gender_male":           "性別",
    "location":              "位置",
}

GROUP_TO_TOKENS = {
    lab: [tok for tok, lbl in TOKEN_TO_LABEL.items() if lbl == lab]
    for lab in set(TOKEN_TO_LABEL.values())
}

# ───────────────── 2. 讀檔、時間欄 ──────────────────────────
print(f"➡️  讀取 {CSV_PATH.name}")
df = pd.read_csv(CSV_PATH)

def _to_dt(x):
    try:
        ts = int(x);  unit = "ms" if ts > 1_000_000_000_000 else "s"
        return pd.to_datetime(ts, unit=unit, utc=True)
    except Exception:
        return pd.to_datetime(x, utc=True, errors="coerce")

df["Timestamp"] = df["Timestamp"].apply(_to_dt)
df = df.dropna(subset=["Timestamp"])
t0 = df["Timestamp"].min()
df["Minute"] = ((df["Timestamp"] - t0).dt.total_seconds() // 60).astype(int)

# ───────────────── 3. 整體 RPS / Latency  (圖 1 ‧ 2) ────────
df_agg = df[df["Name"].str.strip().str.lower() == "aggregated"].copy()
df_agg = df_agg.astype({
    "Requests/s": float,
    "Total Average Response Time": float,
    "Total Median Response Time": float,
    "95%": float,                     # ← 新增 P95 欄
}, errors="ignore")
grp_agg = df_agg.groupby("Minute").mean(numeric_only=True)

# 3-a Requests/min
fig, ax = plt.subplots(figsize=(10,4))
ax.plot(grp_agg.index, grp_agg["Requests/s"]*60,
        lw=2, color="tab:green", label="Requests / min")
ax.set(xlabel="Minutes Since Start", ylabel="Requests / min",
       title="Total Requests per Minute")
ax.legend();  fig.tight_layout();  fig.savefig("loadtest_requests_per_min.png");  plt.close(fig)

# 3-b Latency (Avg / Median / P95)
fig, ax = plt.subplots(figsize=(10,4))
ax.plot(grp_agg.index, grp_agg["Total Average Response Time"]/1000,
        lw=2, label="Avg Latency (s)")
ax.plot(grp_agg.index, grp_agg["Total Median Response Time"]/1000,
        lw=2, ls="--", label="Median Latency P50 (s)")
ax.plot(grp_agg.index, grp_agg["95%"]/1000,
        lw=2, ls=":", label="P95 Latency (s)")           # ← 新增曲線
ax.set(xlabel="Minutes Since Start", ylabel="Latency (s)",
       title="Latency Trend per Minute")
ax.legend();  fig.tight_layout();  fig.savefig("loadtest_latency_trend_per_min.png");  plt.close(fig)
print("✅  圖 1‧2 完成")

# ───────────────── 4. 各指令 RPS  (圖 3) ─────────────────────
df_cmd = df[(df["Type"].str.upper()=="POST") &
            (df["Name"].str.strip().str.lower()!="aggregated")].copy()
if df_cmd.empty:
    print("⚠️  POST rows 為空，跳過圖 3")
else:
    df_cmd["token"]  = df_cmd["Name"].str.split("/").str[-1].str.strip()
    df_cmd["label"]  = df_cmd["token"].map(TOKEN_TO_LABEL).fillna(df_cmd["token"])
    df_cmd["Requests/s"] = pd.to_numeric(df_cmd["Requests/s"], errors="coerce").fillna(0)
    pivot = (df_cmd.groupby(["Minute","label"])["Requests/s"]
                    .mean().unstack(fill_value=0).mul(60))
    fig, ax = plt.subplots(figsize=(12,6))
    cmap = plt.get_cmap("tab20", pivot.shape[1])
    for i, col in enumerate(pivot.columns):
        ax.plot(pivot.index, pivot[col], lw=1.3, color=cmap(i), label=col)
    ax.set(xlabel="Minutes Since Start", ylabel="每分鐘請求數",
           title="各指令每分鐘請求數")
    ax.legend(ncol=2, fontsize=8, loc="upper left")
    fig.tight_layout();  fig.savefig("loadtest_commands_requests_per_min.png");  plt.close(fig)
    print("✅  圖 3 完成（中文 legend）")

# ───────────────── 5. 各分類平均延遲 (圖 4) ────────────────
print("➡️  從 CSV 計算各分類平均延遲…")
df_cmd["Avg_ms"] = pd.to_numeric(df_cmd["Total Average Response Time"], errors="coerce")
df_lat = df_cmd.dropna(subset=["Avg_ms"])[["token","Avg_ms"]].copy()

def _token_to_group(tok:str)->str:
    for grp, toks in GROUP_TO_TOKENS.items():
        if tok in toks:
            return grp
    return "資料收集"   # profile 等歸到這

df_lat["group"] = df_lat["token"].apply(_token_to_group)
grp_latency = (df_lat.groupby("group")["Avg_ms"]
                      .mean().div(1000).sort_values(ascending=False))
print(grp_latency.to_string(float_format="%.3f"))

fig, ax = plt.subplots(figsize=(12,6))
grp_latency.plot(kind="bar", ax=ax, color="tab:blue")
ax.set_xlabel("分類");  ax.set_ylabel("平均延遲 (秒)");  ax.set_title("Average Latency per Group")
plt.xticks(rotation=0, ha="center")
fig.tight_layout();  fig.savefig("loadtest_avg_latency_per_group.png");  plt.close(fig)
print("✅  圖 4 完成\n🎉  全部輸出完成")
