#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Locust script
─────────────
  • 將 JSON payload 放到 ./tests/payloads/ 目錄
  • 在 STEP_WEIGHTS 增加一行 (key=文件名, value=權重)
    Locust 會自動把它納入壓測流程

示例啟動（本機）：
  TARGET_HOST=http://phen-line \
  LINE_CHANNEL_SECRET=your_secret \
  locust -f tests/locustfile.py --headless -u 20 -r 5 -t 2m
"""

import hashlib, hmac, json, os, random, time, uuid
from pathlib import Path
from locust import HttpUser, between, events, task

# ── 0. 參數設定 ───────────────────────────────────────────────
HOST           = os.getenv("TARGET_HOST", "http://localhost:10000")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")   # 留空 ⇒ 不簽章
PAYLOAD_DIR    = Path(__file__).parent / "payloads"

# payload → 權重（數字愈大出現機率愈高）
STEP_WEIGHTS: dict[str, int] = {
    # phase 0：使用者資料蒐集
    "lang_zh":      1,
    "age_25":       1,
    "gender_male":  1,
    "location":     1,
    "text_2days":   1,
    "text_3days":   1,
    "text_4days":   1,
    "text_5days":   1,
    # phase 1：功能指令
    "text_crowd":        2,
    "text_recommend":    2,
    "text_sustain":      1,
    "text_rental":       1,
    "text_restaurants":  1,
    "text_parking":      1,
    "text_scenic_spots": 1,
    "text_accommodation":1,
    # 新增腳本：放 JSON 後在此加一行
    # "new_feature": 1,
}

# ── 1. 修正：開啟 response-times cache ───────────────────────
@events.init.add_listener
def enable_response_times_cache(environment, **_):
    """
    Locust 在寫 full-history CSV 時需要 stats cache。
    若未開啟將在 StatsCSVFileWriter 報 ValueError。
    """
    environment.stats.use_response_times_cache = True

# ── 2. 共用函式 ───────────────────────────────────────────────
def _make_signature(body: bytes) -> str:
    """依 LINE CHANNEL_SECRET 對 body 做 HMAC-SHA256 簽章"""
    return hmac.new(CHANNEL_SECRET.encode(), body, hashlib.sha256).hexdigest()

# ── 3. Locust User 類別 ───────────────────────────────────────
class LineBotUser(HttpUser):
    host = HOST
    wait_time = between(0.3, 1.0)

    # 預載所有 JSON → dict，提升迴圈速度
    _cache: dict[str, dict] = {
        p.stem: json.loads(p.read_text("utf-8-sig"))
        for p in PAYLOAD_DIR.glob("*.json")
    }

    def on_start(self):
        self.uid = str(uuid.uuid4())                 # 每個 VU 一個 UID
        self.hdr = {"Content-Type": "application/json"}

    # ── 送出指定 payload ────────────────────────────────────
    def _post(self, name: str):
        if name not in self._cache:
            raise ValueError(f"payload '{name}.json' not found")

        # 深複製 → 填入動態欄位
        payload = json.loads(json.dumps(self._cache[name]))
        payload["events"][0]["replyToken"] = str(uuid.uuid4())
        payload["events"][0]["source"]["userId"] = self.uid
        payload["events"][0]["timestamp"] = int(time.time() * 1000)
        body = json.dumps(payload).encode("utf-8")

        # 需簽章則加上 Header
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
        except Exception as exc:
            # 送出失敗仍上報給 Locust，不中斷其他任務
            self.environment.events.request.fire(
                request_type="PAYLOAD",
                name=f"{payload_name}.json",
                response_time=0,
                response_length=0,
                exception=exc,
            )

# ── 4. 測試結束鉤子 → 儲存自訂報表 ──────────────────────────
from locust_db import save_stats  # 若不需要可移除

@events.test_stop.add_listener
def on_test_stop(environment, **_):
    stats = environment.runner.stats.total
    print(
        f"\nRequests : {stats.num_requests}  |  "
        f"Failures : {stats.num_failures}  |  "
        f"P95 : {stats.get_response_time_percentile(0.95):.0f} ms"
    )
    try:
        save_stats(environment)
    except Exception as e:
        print(f"[locustfile] save_stats failed: {e}")
