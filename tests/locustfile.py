#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Locust script
─────────────
  • 只要把 JSON payload 放到 ./tests/payloads/ 目錄
  • 在 STEP_WEIGHTS 增加一行 (key=檔名, value=權重)
    Locust 就會自動把它加入壓測流程

啟動範例：
  APP_ENV=loadtest \
  locust -f tests/locustfile.py --headless -u 20 -r 5 -t 2m
"""

# ── 基本 import ─────────────────────────────────────────────
import hashlib
import hmac
import json
import os
import random
import time
import uuid
from pathlib import Path

from locust import HttpUser, between, events, task

# ── 0. 參數設定 ───────────────────────────────────────────────
HOST           = os.getenv("TARGET_HOST", "http://localhost:8000")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")   # 留空 ⇒ 不簽章
PAYLOAD_DIR    = Path(__file__).parent / "payloads"

# payload → 權重　（數字愈大出現機率愈高）
STEP_WEIGHTS: dict[str, int] = {
    # ── phase 0：使用者資料蒐集
    "lang_zh":      1,
    "age_25":       1,
    "gender_male":  1,
    "location":     1,
    "text_2days":   1,
    "text_3days":   1,
    "text_4days":   1,
    "text_5days":   1,

    # ── phase 1：功能指令
    "text_crowd":       2,
    "text_recommend":   2,
    "text_sustain":     1,
    "text_rental":      1,
    "text_restaurants": 1,
    "text_parking":     1,
    "text_scenic_spots":1,
    "text_accommodation":1,

    # ★★★　要新增腳本？只要：    1) 放 json；2) 下面加一行即可
    # "new_feature": 1,
}

# ── 1. 共用函式 ───────────────────────────────────────────────
def _make_signature(body: bytes) -> str:
    return hmac.new(CHANNEL_SECRET.encode(), body, hashlib.sha256).hexdigest()


# ── 2. Locust User 類別 ───────────────────────────────────────
class LineBotUser(HttpUser):
    host = HOST
    wait_time = between(0.3, 1.0)

    # 一次把全部 json 讀進記憶體，加快迴圈速度
    _cache: dict[str, str] = {
        p.stem: p.read_text("utf-8") for p in PAYLOAD_DIR.glob("*.json")
    }

    def on_start(self):
        self.uid = str(uuid.uuid4())
        self.hdr = {"Content-Type": "application/json"}

    # ── 送出指定 payload ────────────────────────────────────
    def _post(self, name: str):
        if name not in self._cache:
            raise ValueError(f"payload '{name}.json' not found")

        body = (
            self._cache[name]
            .replace("__USERID__", self.uid)
            .replace("__TIMESTAMP__", str(int(time.time() * 1000)))
        ).encode("utf-8")

        # LINE webhook 需要簽章就帶上
        if CHANNEL_SECRET:
            self.hdr["X-Line-Signature"] = _make_signature(body)

        self.client.post("/", data=body, headers=self.hdr, name=f"POST / {name}")

    # ── 單一 task：每次隨機挑一個 payload 送出 ───────────────
    @task
    def run_all_steps(self):
        payload_name = random.choices(
            population=list(STEP_WEIGHTS),
            weights=list(STEP_WEIGHTS.values()),
            k=1,
        )[0]
        try:
            self._post(payload_name)
        except Exception as exc:  # 送出失敗時仍回報給 Locust
            self.environment.events.request.fire(
                request_type="PAYLOAD",
                name=f"{payload_name}.json",
                response_time=0,
                response_length=0,
                exception=exc,
            )


# ── 3. 測試結束 → 寫入自訂 SQLite 報表 ───────────────────────
from locust_db import save_stats  # 你的 util，若沒有可自行移除

@events.test_stop.add_listener
def _(environment, **kw):
    stats = environment.runner.stats.total
    print(
        f"\nRequests : {stats.num_requests}  |  "
        f"Failures : {stats.num_failures}  |  "
        f"P95 : {stats.get_response_time_percentile(0.95):.0f} ms"
    )
    # 若有自訂報表
    try:
        save_stats(environment)
    except Exception as e:  # 寫 DB 失敗不要影響 Locust 主流程
        print(f"[locustfile] save_stats failed: {e}")
