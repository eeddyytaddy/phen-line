#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Locust script (placeholder-friendly)
────────────────────────────────────────────
‧ ./tests/payloads/*.json 允許 "__USERID__" "__TIMESTAMP__"
‧ 送出前動態替換成隨機 uid 與現在 timestamp(ms)
"""

import json
import os
import time
import uuid
from pathlib import Path
from typing import Final

from locust import HttpUser, between, events, task

# ─── 0. 基本設定 ──────────────────────────────────────────
BASE_DIR: Final[Path] = Path(__file__).parent
PAYLOAD_DIR: Final[Path] = BASE_DIR / "payloads"

HOST_DEFAULT = "http://phen-line:10000"
HOST = os.getenv("TARGET_HOST", HOST_DEFAULT)

STEP_WEIGHTS = {
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

# ─── 1. Locust User ───────────────────────────────────────
class LineBotUser(HttpUser):
    host = HOST
    wait_time = between(0.3, 1.0)

    # ∘ 先把 json 原始字串讀進 cache
    _cache_txt: dict[str, str] = {
        p.stem: p.read_text("utf-8") for p in PAYLOAD_DIR.glob("*.json")
    }

    def on_start(self):
        self.uid = str(uuid.uuid4())                 # 每個使用者一個 uid
        self.headers = {"Content-Type": "application/json"}

    # --------- 單一 POST（動態替換 placeholder）-------------
    def _post(self, payload_name: str):
        txt = self._cache_txt[payload_name]
        txt = (
            txt.replace("__USERID__", self.uid)
               .replace("__TIMESTAMP__", str(int(time.time() * 1000)))
        )
        body = json.loads(txt)                       # 轉回 dict

        self.client.post(
            "/v1/endpoint",                          # <<< API 路徑
            json=body,                               # 自動 UTF-8
            headers=self.headers,
            name=payload_name,                       # 分流名稱
        )

    # --------- 動態註冊 task -------------------------------
    for _name, _weight in STEP_WEIGHTS.items():

        def _make_task(name=_name):
            @task(weight=STEP_WEIGHTS[name])
            def _(self):
                self._post(name)

            return _

        locals()[f"task_{_name}"] = _make_task()

# ─── 2. (Optional) 測試結束寫入 DB ────────────────────────
try:
    from locust_db import save_stats
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
