#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Locust 壓測腳本
────────────────────────────────────────────────────────────
  • 將要打的 JSON payload (*.json) 放到 ./tests/payloads/
  • 在 STEP_WEIGHTS 加入權重，Locust 會依比例隨機抽 task
"""

import json
import os
import uuid
from pathlib import Path
from typing import Final

from locust import HttpUser, between, events, task

# ────────── 0. 路徑與目標主機 ──────────────────────────────
BASE_DIR: Final[Path] = Path(__file__).parent
PAYLOAD_DIR: Final[Path] = BASE_DIR / "payloads"

# 內網 URL（同一 Railway environment 下最穩，也不計流量）
HOST_DEFAULT = "http://phen-line:10000"
HOST = os.getenv("TARGET_HOST", HOST_DEFAULT)  # 部署時可用 env 覆蓋

# ────────── 1. 每支 payload 的權重 ─────────────────────────
STEP_WEIGHTS: dict[str, int] = {
    "age_25": 1,
    "gender_male": 1,
    "lang_zh": 1,
    "location": 1,
    "text_2days": 1,
    "text_3days": 1,
    "text_4days": 1,
    "text_5days": 1,
    "text_accommodation": 1,
    "text_crowd": 2,
    "text_parking": 1,
    "text_recommend": 2,
    "text_rental": 1,
    "text_restaurants": 1,
    "text_scenic_spots": 1,
    "text_sustain": 1,
}

# ────────── 2. Locust User 類別 ────────────────────────────
class LineBotUser(HttpUser):
    host = HOST
    wait_time = between(0.3, 1.0)

    # 預先把所有 JSON 讀進記憶體（dict）
    _cache: dict[str, dict] = {
        p.stem: json.loads(p.read_text("utf-8")) for p in PAYLOAD_DIR.glob("*.json")
    }

    def on_start(self):
        self.uid = str(uuid.uuid4())
        self.headers = {"Content-Type": "application/json"}

    # ----------- 單一 POST 動作（使用 json= 以 UTF-8 傳送） -----------
    def _post(self, payload_name: str):
        body = self._cache[payload_name].copy()
        body["uid"] = self.uid  # 假設 payload 需要 uid，可移除此行
        self.client.post(
            url="/v1/endpoint",          # <<< API 真實路徑請改這裡
            json=body,                   # 用 json= 自動 UTF-8
            headers=self.headers,
            name=payload_name,
        )

    # ----------- 動態註冊 Task ----------------------------------------
    for _name, _weight in STEP_WEIGHTS.items():

        def _make_task(name=_name):      # 預設參數鎖定字串
            @task(weight=STEP_WEIGHTS[name])
            def _(self):
                self._post(name)
            return _

        locals()[f"task_{_name}"] = _make_task()

# ────────── 3. 測試結束時可寫入自訂 DB（可刪） ─────────────────
try:
    from locust_db import save_stats  # 若沒有這工具檔可以刪掉整段
except ImportError:
    save_stats = None

@events.test_stop.add_listener
def _(env, **kw):
    if not save_stats:
        return
    s = env.runner.stats.total
    save_stats(
        host=env.host,
        run_time=env.parsed_options.run_time,
        total_rps=s.total_rps,
        total_fail_per_sec=s.total_fail_per_sec,
        failures=s.num_failures,
        successes=s.num_requests,
        avg_resp_time_ms=s.avg_response_time,
    )
