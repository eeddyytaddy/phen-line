#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Locust script – 支援 __USERID__/__TIMESTAMP__ placeholder
"""

import json, os, time, uuid
from pathlib import Path
from locust import HttpUser, between, task, events

BASE_DIR = Path(__file__).parent
PAYLOAD_DIR = BASE_DIR / "payloads"

HOST = os.getenv("TARGET_HOST", "http://phen-line:10000")  # 內網預設

STEP_WEIGHTS = {
    "age_25": 1, "gender_male": 1, "lang_zh": 1, "location": 1,
    "text_2days": 1, "text_3days": 1, "text_4days": 1, "text_5days": 1,
    "text_accommodation": 1, "text_crowd": 2, "text_parking": 1,
    "text_recommend": 2, "text_rental": 1, "text_restaurants": 1,
    "text_scenic_spots": 1, "text_sustain": 1,
}

class LineBotUser(HttpUser):
    host = HOST
    wait_time = between(0.3, 1.0)

    # 讀檔用 utf-8-sig，自動剝掉 BOM
    _cache_txt = {
        p.stem: p.read_text("utf-8-sig") for p in PAYLOAD_DIR.glob("*.json")
    }

    def on_start(self):
        self.uid = str(uuid.uuid4())
        self.headers = {"Content-Type": "application/json"}

    def _post(self, name: str):
        txt = (self._cache_txt[name]
               .replace("__USERID__", self.uid)
               .replace("__TIMESTAMP__", str(int(time.time() * 1000))))
        self.client.post(
            "/v1/endpoint",                 # ⇦ 請改成真實 API 路徑
            json=json.loads(txt),           # json= 自帶 UTF-8
            headers=self.headers,
            name=name,
        )

    # ── 動態產生 task：名稱與權重都綁定進預設參數 ──
    for _n, _w in STEP_WEIGHTS.items():

        def _make(name=_n, weight=_w):
            @task(weight=weight)
            def _(self):
                self._post(name)
            return _

        locals()[f"task_{_n}"] = _make()

# 若用不到 DB 統計，整段可刪
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
