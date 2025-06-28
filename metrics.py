# metrics.py  —— Prometheus 指標 ＋ 系統資源監控
# ==============================================
from __future__ import annotations

import threading
import time
import psutil

from flask import request, Response
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

# ───────────────────────────────────────────────
# 0. 模組層級旗標：避免重複初始 & 多執行緒
# ───────────────────────────────────────────────
_INITIALIZED = False
_RES_MONITOR_RUNNING = False

# ───────────────────────────────────────────────
# 1. HTTP Request 指標
# ───────────────────────────────────────────────
REQ_COUNTER = Counter(
    name="http_requests_total",
    documentation="Total HTTP requests",
    labelnames=("endpoint", "method", "status_code"),
)

LATENCY_HIST = Histogram(
    name="http_request_latency_seconds",
    documentation="HTTP request latency in seconds",
    labelnames=("endpoint", "method"),
    buckets=(
        0.005,
        0.01,
        0.025,
        0.05,
        0.075,
        0.1,
        0.25,
        0.5,
        0.75,
        1,
        2,
        5,
        10,
    ),
)


def _register_http_hooks(app):
    """在 Flask app 上掛 before_request / after_request 蒐集指標"""

    @app.before_request
    def _start_timer():  # pylint: disable=unused-variable
        request._start_time = time.perf_counter()

    @app.after_request
    def _record_metrics(resp):  # pylint: disable=unused-variable
        elapsed = (
            time.perf_counter() - getattr(request, "_start_time", time.perf_counter())
        )
        LATENCY_HIST.labels(request.path, request.method).observe(elapsed)

        REQ_COUNTER.labels(request.path, request.method, resp.status_code).inc()
        return resp


# ───────────────────────────────────────────────
# 2. 系統資源監控（Gauge）—— 單執行緒每 N 秒更新
# ───────────────────────────────────────────────
CPU_GAUGE = Gauge("system_cpu_percent", "System-wide CPU usage (%)")
MEM_GAUGE = Gauge("system_mem_percent", "System-wide Memory usage (%)")


def _resource_loop(interval: int = 5):
    global _RES_MONITOR_RUNNING
    _RES_MONITOR_RUNNING = True
    print(f"[resource_monitor] Started (interval={interval}s)")
    while _RES_MONITOR_RUNNING:
        CPU_GAUGE.set(psutil.cpu_percent())
        MEM_GAUGE.set(psutil.virtual_memory().percent)
        time.sleep(interval)


def _start_resource_monitor(interval: int = 5):
    if not _RES_MONITOR_RUNNING:
        threading.Thread(
            target=_resource_loop, args=(interval,), daemon=True
        ).start()


# ───────────────────────────────────────────────
# 3. 外部呼叫入口
# ───────────────────────────────────────────────
def init_metrics(app, resource_interval: int = 5):
    """
    在 app.py 裡呼叫：
        import metrics
        metrics.init_metrics(app, resource_interval=5)
    之後即可瀏覽 http://<host>:<port>/prometheus 取得 metrics
    """
    global _INITIALIZED
    if _INITIALIZED:                 # 第二次呼叫就直接跳過
        return
    _INITIALIZED = True

    # ① HTTP 勾子
    _register_http_hooks(app)

    # ② 系統資源
    _start_resource_monitor(resource_interval)

    # ③ /prometheus 匯出端點
    @app.route("/prometheus")
    def prometheus_exporter():  # pylint: disable=unused-variable
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
