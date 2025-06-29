#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Locust script
─────────────
  • 将 JSON payload 放到 ./tests/payloads/ 目录
  • 在 STEP_WEIGHTS 增加一行 (key=文件名, value=权重)
    Locust 会自动把它纳入压测流程

示例启动：
  TARGET_HOST=http://phen-line \
  LINE_CHANNEL_SECRET=your_secret \
  locust -f tests/locustfile.py --headless -u 20 -r 5 -t 2m
"""

import hashlib
import hmac
import json
import os
import random
import time
import uuid
from pathlib import Path

from locust import HttpUser, between, events, task

# ── 0. 参数设定 ───────────────────────────────────────────────
HOST           = os.getenv("TARGET_HOST", "http://localhost:10000")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")   # 留空 ⇒ 不签章
PAYLOAD_DIR    = Path(__file__).parent / "payloads"

# payload → 权重（数字越大出现概率越高）
STEP_WEIGHTS: dict[str, int] = {
    # ── phase 0：用户资料收集
    "lang_zh":      1,
    "age_25":       1,
    "gender_male":  1,
    "location":     1,
    "text_2days":   1,
    "text_3days":   1,
    "text_4days":   1,
    "text_5days":   1,

    # ── phase 1：功能指令
    "text_crowd":        2,
    "text_recommend":    2,
    "text_sustain":      1,
    "text_rental":       1,
    "text_restaurants":  1,
    "text_parking":      1,
    "text_scenic_spots": 1,
    "text_accommodation":1,

    # 如需新增脚本：放入 JSON 文件，然后在此添加一行即可
    # "new_feature": 1,
}

# ── 1. 共用签名函数 ────────────────────────────────────────────
def _make_signature(body: bytes) -> str:
    return hmac.new(CHANNEL_SECRET.encode(), body, hashlib.sha256).hexdigest()

# ── 2. Locust User 类别 ───────────────────────────────────────
class LineBotUser(HttpUser):
    host = HOST
    wait_time = between(0.3, 1.0)

    # 预读取所有 JSON 到内存，加速循环
    _cache: dict[str, str] = {
        p.stem: p.read_text("utf-8") for p in PAYLOAD_DIR.glob("*.json")
    }

    def on_start(self):
        # 每个虚拟用户一个唯一 ID
        self.uid = str(uuid.uuid4())
        self.hdr = {"Content-Type": "application/json"}

    def _post(self, name: str):
        if name not in self._cache:
            raise ValueError(f"payload '{name}.json' not found")

        # 动态替换占位符
        body = (
            self._cache[name]
            .replace("__USERID__", self.uid)
            .replace("__TIMESTAMP__", str(int(time.time() * 1000)))
        ).encode("utf-8")

        # 如果需要签章，就加入 HEADER
        if CHANNEL_SECRET:
            self.hdr["X-Line-Signature"] = _make_signature(body)

        # 发送请求
        self.client.post("/", data=body, headers=self.hdr, name=f"POST / {name}")

    @task
    def run_all_steps(self):
        # 随机选择一个 payload 发送
        payload_name = random.choices(
            population=list(STEP_WEIGHTS),
            weights=list(STEP_WEIGHTS.values()),
            k=1,
        )[0]
        try:
            self._post(payload_name)
        except Exception as exc:
            # 捕获异常并上报给 Locust，不中断其他任务
            self.environment.events.request.fire(
                request_type="PAYLOAD",
                name=f"{payload_name}.json",
                response_time=0,
                response_length=0,
                exception=exc,
            )

# ── 3. 测试结束钩子 → 保存自定义报表 ───────────────────────────
from locust_db import save_stats  # 若不需要可移除此行

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    stats = environment.runner.stats.total
    print(
        f"\nRequests : {stats.num_requests}  |  "
        f"Failures : {stats.num_failures}  |  "
        f"P95      : {stats.get_response_time_percentile(0.95):.0f} ms"
    )
    # 调用你的保存逻辑（写入 SQLite 等）
    try:
        save_stats(environment)
    except Exception as e:
        print(f"[locustfile] save_stats failed: {e}")
