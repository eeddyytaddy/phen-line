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
import os
import random
import uuid
from pathlib import Path
from typing import Final

from locust import HttpUser, between, events, task

# ── 0. 目錄 & 檔案設定 ─────────────────────────────────────────
BASE_DIR: Final[Path] = Path(__file__).parent
PAYLOAD_DIR: Final[Path] = BASE_DIR / "payloads"

# ── 1. 測試目標主機 (★ 這行改了預設值) ───────────────────────
#   · 若部署時有設定環境變數 TARGET_HOST，會優先採用
#   · 否則預設指向同一個 Railway 專案內的 phen-line 服務
HOST           = os.getenv("TARGET_HOST", "http://phen-line:10000")

# ── 2. 每支 payload 的權重（要跑哪些 JSON）──────────────────
#     key = ./payloads/{key}.json
#     value = 權重 (出現的機率)
STEP_WEIGHTS = {
    "age_25":            1,
    "gender_male":       1,
    "lang_zh":           1,
    "location":          1,
    "text_2days":        1,
    "text_3days":        1,
    "text_4days":        1,
    "text_5days":        1,
    "text_accommodation":1,
    "text_crowd":        2,
    "text_parking":      1,
    "text_recommend":    2,
    "text_rental":       1,
    "text_restaurants":  1,
    "text_scenic_spots": 1,
    "text_sustain":      1,
}

# ────────────────────────────────────────────────────────────
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
    def _post(self, payload_name: str):
        body = self._cache[payload_name]
        self.client.post(
            "/v1/endpoint",  # ← 若路徑不是 /v1/endpoint，請改成 API 真實路徑
            data=body.replace("{uid}", self.uid),
            headers=self.hdr,
            name=payload_name,
        )

    # ── 依權重動態產生 Locust tasks ──────────────────────────
    for _name, _weight in STEP_WEIGHTS.items():

        def _make_task(payload=_name):  # default arg 捕捉 loop 變數
            @task(weight=STEP_WEIGHTS[payload])
            def _(self):
                self._post(payload)

            return _

        locals()[f"task_{_name}"] = _make_task()

# ── 3. 測試結束 → 寫入自訂 SQLite 報表 ───────────────────────
from locust_db import save_stats  # 若沒有 util，可註解掉

@events.test_stop.add_listener
def _(environment, **kw):
    stats = environment.runner.stats.total
    save_stats(
        host=environment.host,
        run_time=environment.parsed_options.run_time,
        total_rps=stats.total_rps,
        total_fail_per_sec=stats.total_fail_per_sec,
        failures=stats.num_failures,
        successes=stats.num_requests,
        avg_resp_time_ms=stats.avg_response_time,
    )
