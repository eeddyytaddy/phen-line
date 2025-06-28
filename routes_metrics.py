"""
routes_metrics.py  –  圖表總管  (v2, 2025-06-24)
================================================
原本已有 3 張圖：
    • /metrics/stacked_resource_by_cmd.png
    • /metrics/runtime_resource_trend.png
    • /metrics/locust_trend.png

本版 **再加 4 張**：
    • /metrics/fn_latency_box.png        —— 盒鬚圖：各函式延遲分佈
    • /metrics/fn_cpu_mem_scatter.png    —— 散點圖：CPU × Mem（氣泡大小 = P95）
    • /metrics/locust_fail_bar.png       —— 長條圖：各端點失敗率
    • /metrics/fn_heatmap.png            —— 熱力圖：函式 × 5 min bucket 平均延遲

使用方法：
    import routes_metrics
    routes_metrics.register_png_routes(app)
"""
from __future__ import annotations
import io, os, sqlite3
from typing import Dict, List
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from flask import Blueprint, request, send_file
import time

# ───────────────────── 基本設定 ─────────────────────
try:
    from config import D1_BINDING, LOCUST_DB      # 同一顆 DB
except ImportError:                               # 沒有 config.py 時
    D1_BINDING = os.getenv("D1_BINDING", "metrics.db")
    LOCUST_DB = os.getenv("LOCUST_DB",  D1_BINDING)

bp = Blueprint("metrics_png", __name__)

def _connect(db: str) -> sqlite3.Connection:      # autocommit + busy-timeout
    return sqlite3.connect(db,
                           detect_types=sqlite3.PARSE_DECLTYPES,
                           isolation_level=None, timeout=5.0)

# ─────────────── function_runtime 5 min 聚合 ───────────────
def _has_view(con: sqlite3.Connection, v: str) -> bool:
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='view' AND name=?", (v,)
    ).fetchone())

def fetch_fn_5m(hours: int = 24) -> pd.DataFrame:
    since = pd.Timestamp.utcnow() - pd.Timedelta(hours=hours)
    since_ms = int(since.timestamp()*1000)
    with _connect(D1_BINDING) as con:
        if _has_view(con, "v_fn_5m_avg"):
            sql = "SELECT * FROM v_fn_5m_avg WHERE bucket_ms>=?"
            df = pd.read_sql(sql, con, params=(since_ms,))
            if df.empty: return df
            df["ts"] = pd.to_datetime(df["bucket_ms"], unit="ms")
            return df.set_index("ts")
        # ─ 手動分桶 ─
        raw = pd.read_sql(
            """SELECT ts,fn,duration_ms,cpu_percent,mem_percent,concurrent_users
               FROM   function_runtime WHERE ts>=?""",
            con, params=(since_ms,))
    if raw.empty: return raw
    raw["ts"] = pd.to_datetime(raw["ts"], unit="ms").dt.floor("5min")
    g = raw.groupby(["fn","ts"])
    agg = (g.agg(reqs=("duration_ms","size"),
                 avg_duration_ms=("duration_ms","mean"),
                 p95_dur_ms=("duration_ms", lambda x: x.quantile(.95)),
                 avg_cpu=("cpu_percent","mean"),
                 avg_mem=("mem_percent","mean"),
                 avg_users=("concurrent_users","mean"))
             .reset_index())
    return agg.set_index("ts")

# ────────────────────── Locust 5 min 聚合 ──────────────────────
def fetch_ls_5m(hours: int = 24) -> pd.DataFrame:
    since = pd.Timestamp.utcnow() - pd.Timedelta(hours=hours)
    since_ms = int(since.timestamp()*1000)
    with _connect(LOCUST_DB) as con:
        if _has_view(con, "v_ls_5m_rate"):
            df = pd.read_sql("SELECT * FROM v_ls_5m_rate WHERE bucket_ms>=?",
                             con, params=(since_ms,))
            if df.empty: return df
            df["ts"] = pd.to_datetime(df["bucket_ms"], unit="ms")
            return df
        # ─ 回退 ─
        raw = pd.read_sql(
            "SELECT ts,endpoint,method,avg_ms,p95_ms,rps,failures "
            "FROM locust_stats WHERE ts>=?", con, params=(since_ms,))
    if raw.empty: return raw
    raw["ts"] = pd.to_datetime(raw["ts"], unit="ms").dt.floor("5min")
    agg = (raw.groupby(["endpoint","ts"])
              .agg(avg_rps=("rps","mean"),
                   p95_ms=("p95_ms","mean"),
                   fail_rate=("failures", lambda x: x.sum() / max(1, x.count())))
              .reset_index())
    return agg

# ───────────────────── 4 個原有 / 新圖表 ─────────────────────
def _plain_png(fig) -> bytes:
    buf = io.BytesIO(); fig.tight_layout(); fig.savefig(buf, format="png"); plt.close(fig); buf.seek(0); return buf

# 1. 橫向堆疊長條：Avg CPU vs Mem (by command)  ── 原本就有
@bp.route("/metrics/stacked_resource_by_cmd.png")
def stacked_resource_by_cmd_png():
    hours = int(request.args.get("hours",24))
    df = fetch_fn_5m(hours)
    if df.empty: return "No data",404
    pipeline: Dict[str,List[str]] = {
        "2days":["run_ml_sort_兩天一夜","run_filter_兩天一夜",
                 "run_ranking_兩天一夜","run_upload_兩天一夜"],
        "3days":["run_ml_sort_三天兩夜","run_filter_三天兩夜",
                 "run_ranking_三天兩夜","run_upload_三天兩夜"],
        "4days":["run_ml_sort_四天三夜","run_filter_四天三夜",
                 "run_ranking_四天三夜","run_upload_四天三夜"],
        "5days":["run_ml_sort_五天四夜","run_filter_五天四夜",
                 "run_ranking_五天四夜","run_upload_五天四夜"],
    }
    g = df.groupby("fn")[["avg_cpu","avg_mem"]].mean()
    mean = lambda fns,col: g.reindex(fns)[col].mean() if g.index.intersection(fns).any() else 0
    cpu = {k:mean(v,"avg_cpu") for k,v in pipeline.items()}
    mem = {k:mean(v,"avg_mem") for k,v in pipeline.items()}
    fig,ax = plt.subplots(figsize=(8,4))
    y = range(len(cpu))
    ax.barh(y,list(cpu.values()),label="CPU%",color="steelblue")
    ax.barh(y,list(mem.values()),left=list(cpu.values()),label="Mem%",color="peachpuff")
    ax.set_yticks(list(y)); ax.set_yticklabels(list(cpu.keys())); ax.set_xlabel("Average Usage (%)")
    ax.set_title(f"Avg CPU & Mem by Command (last {hours} h)")
    ax.grid(axis="x",linestyle="--",alpha=.3); ax.legend()
    return send_file(_plain_png(fig),mimetype="image/png")

# 2. 趨勢線：單函式 runtime / cpu / mem / users  ── 原本就有
@bp.route("/metrics/runtime_resource_trend.png")
def runtime_resource_trend_png():
    hours=int(request.args.get("hours",6)); fn=request.args.get("fn")
    df=fetch_fn_5m(hours);   # 同上
    if df.empty: return "No data",404
    if fn: df=df[df["fn"]==fn]
    else : df=(df.groupby(df.index)
                 .agg(avg_duration=("avg_duration_ms","mean"),
                      p95=("p95_dur_ms","mean"),
                      cpu=("avg_cpu","mean"), mem=("avg_mem","mean"),
                      users=("avg_users","mean")))
    fig,ax1=plt.subplots(figsize=(10,4))
    ax1.plot(df.index,df["avg_duration"]/1000,label="Avg (s)",color="tab:blue")
    ax1.plot(df.index,df["p95"]/1000,"--",label="P95 (s)",color="tab:blue")
    ax1.set_ylabel("Runtime (s)",color="tab:blue"); ax1.tick_params(labelcolor="tab:blue")
    ax2=ax1.twinx()
    ax2.plot(df.index,df["cpu"],label="CPU%",color="tab:red")
    ax2.plot(df.index,df["mem"],label="Mem%",color="tab:green")
    if "users" in df: ax2.plot(df.index,df["users"],label="Users",color="tab:purple")
    ax2.set_ylabel("CPU / Mem % · Users",color="tab:red"); ax2.tick_params(labelcolor="tab:red")
    ax1.set_title(f"{fn or 'ALL'} – Runtime / Resource Trend (last {hours} h)")
    fig.legend(loc="upper left",bbox_to_anchor=(0.08,0.92),ncol=3)
    return send_file(_plain_png(fig),mimetype="image/png")

# 3. Locust RPS + Overall P95  ── 原本就有
@bp.route("/metrics/locust_trend.png")
def locust_trend_png():
    hours=int(request.args.get("hours",24)); df=fetch_ls_5m(hours)
    if df.empty: return "No locust data",404
    fig,ax1=plt.subplots(figsize=(10,4))
    for ep in df["endpoint"].unique():
        sub=df[df["endpoint"]==ep]; ax1.plot(sub["ts"],sub["avg_rps"],marker="o",label=f"{ep} RPS")
    ax1.set_ylabel("Requests / s"); ax1.set_xlabel("Time")
    ax1.grid(axis="x",ls="--",alpha=.3); ax1.legend(ncol=2,fontsize=7)
    ax2=ax1.twinx(); p95=(df.groupby("ts")["p95_ms"].mean()/1000)
    ax2.plot(p95.index,p95.values,"k--",label="Overall P95 (s)")
    ax2.set_ylabel("P95 Latency (s)"); ax2.legend()
    ax1.set_title(f"Locust Trend (last {hours} h)")
    return send_file(_plain_png(fig),mimetype="image/png")

# 4. 盒鬚圖：函式延遲分佈
@bp.route("/metrics/fn_latency_box.png")
def fn_latency_box():
    hours=int(request.args.get("hours",6)); df=fetch_fn_5m(hours)
    if df.empty: return "No data",404
    fig,ax=plt.subplots(figsize=(10,4))
    order=df["fn"].unique()
    data=[df[df["fn"]==f]["avg_duration_ms"]/1000 for f in order]
    ax.boxplot(data,labels=order,showfliers=False)
    ax.set_ylabel("Avg Runtime (s)"); ax.set_title(f"Latency Distribution per Function (last {hours} h)")
    ax.grid(axis="y",ls="--",alpha=.3); plt.xticks(rotation=25,ha="right")
    return send_file(_plain_png(fig),mimetype="image/png")

# 5. 散點圖：CPU vs Mem（氣泡 = P95）
@bp.route("/metrics/fn_cpu_mem_scatter.png")
def fn_cpu_mem_scatter():
    hours=int(request.args.get("hours",6)); df=fetch_fn_5m(hours)
    if df.empty: return "No data",404
    g=df.groupby("fn").agg(cpu=("avg_cpu","mean"),mem=("avg_mem","mean"),
                           p95=("p95_dur_ms","mean"))
    fig,ax=plt.subplots(figsize=(6,6))
    for fn,row in g.iterrows():
        ax.scatter(row["cpu"],row["mem"],s=(row["p95"]/1000)*40,alpha=.6,label=fn)
        ax.text(row["cpu"],row["mem"],fn,fontsize=8)
    ax.set_xlabel("CPU %"); ax.set_ylabel("Mem %")
    ax.set_title(f"CPU vs Mem (bubble=P95, last {hours} h)"); ax.grid(ls="--",alpha=.3)
    return send_file(_plain_png(fig),mimetype="image/png")

# 6. 長條圖：Locust 失敗率
@bp.route("/metrics/locust_fail_bar.png")
def locust_fail_bar():
    hours=int(request.args.get("hours",24)); df=fetch_ls_5m(hours)
    if df.empty: return "No locust data",404
    g=df.groupby("endpoint")["fail_rate"].mean().sort_values(ascending=False)
    fig,ax=plt.subplots(figsize=(8,4)); g.plot.bar(ax=ax,color="salmon")
    ax.set_ylabel("Failure rate"); ax.set_xlabel("Endpoint")
    ax.set_title(f"Average Failure Rate (last {hours} h)")
    plt.xticks(rotation=45,ha="right")
    return send_file(_plain_png(fig),mimetype="image/png")

# 7. 熱力圖：函式 × 時間 bucket 平均延遲
@bp.route("/metrics/fn_heatmap.png")
def fn_heatmap():
    hours = int(request.args.get("hours", 24))
    df = fetch_fn_5m(hours)
    if df.empty:
        return "No data", 404

    # 轉成：行＝fn，列＝時間 bucket，值＝平均延遲（秒）
    pivot = (df.reset_index()               # ts 還在 index → 先展開
               .pivot_table(index="fn",
                            columns="ts",   # 5-min bucket
                            values="avg_duration_ms",
                            aggfunc="mean") / 1000.0)

    fig, ax = plt.subplots(figsize=(pivot.shape[1] * 0.45 + 3, 4))
    im = ax.imshow(pivot, aspect="auto", cmap="YlOrRd")

    # X 軸刻度：只標有限個，以免擠在一起
    ax.set_xticks(range(pivot.shape[1]))
    ax.set_xticklabels([c.strftime("%m-%d %H:%M") for c in pivot.columns],
                       rotation=45, ha="right", fontsize=8)

    ax.set_yticks(range(pivot.shape[0]))
    ax.set_yticklabels(pivot.index, fontsize=9)

    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("Avg runtime (s)")

    ax.set_title(f"Function latency heat-map (last {hours} h)")
    return send_file(_plain_png(fig), mimetype="image/png")


# ─────────────────── Blueprint 註冊 ───────────────────
def register_png_routes(app): app.register_blueprint(bp)
