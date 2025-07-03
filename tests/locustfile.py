#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Locust script  – auto-stop + safe CSV + stats cache
────────────────────────────────────────────────────
環境變數（皆可選）  
  RUN_TIME_SEC   壓測總秒數，預設 600 (=10 min)  
  SLEEP_ON_END   測試結束後保留容器存活秒數，預設 300  
                 ＝你可在這段時間 railway ssh 下載 /data/*.csv
"""

# ── 0. 補丁：分號 CSV & 啟用 stats cache ──────────────────────
import os, csv
from locust import stats as _stats, events

# 0-a  ➜ 讓 full-history CSV 用「;」且所有文字欄位加引號
class _PatchedWriter(_stats.StatsCSVFileWriter):
    def __init__(self, env, base):
        super().__init__(env, base)
        self.stats_history_file.seek(0)
        self.stats_history_file.truncate(0)
        self.stats_history_csv_writer = csv.writer(
            self.stats_history_file,
            delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\n"
        )
        self.stats_history_csv_writer.writerow(self.STATS_HISTORY_CSV_HEADERS)
        self.stats_history_file.flush()
_stats.StatsCSVFileWriter = _PatchedWriter

# 0-b  ➜ 在 Environment 建好後立即開啟 response-times cache
@events.init.add_listener
def _enable_cache(env, **_):
    env.stats.use_response_times_cache = True

# ── 1. 自動停止 & 保活 ───────────────────────────────────────
from gevent import spawn_later, sleep as gsleep

RUN_TIME_SEC = int(os.getenv("RUN_TIME_SEC", "600"))
SLEEP_KEEP   = int(os.getenv("SLEEP_ON_END", "300"))

@events.test_start.add_listener
def _schedule_stop(env, **_):
    spawn_later(RUN_TIME_SEC, lambda: env.runner and env.runner.quit())

@events.test_stop.add_listener
def _keep_alive(env, **_):
    if SLEEP_KEEP > 0:
        print(f"[keep-alive] 容器將於 {SLEEP_KEEP}s 後退出")
        gsleep(SLEEP_KEEP)

# ── 2. 壓測邏輯 ─────────────────────────────────────────────
import hashlib, hmac, json, random, time, uuid
from pathlib import Path
from locust import HttpUser, between, task

HOST           = os.getenv("TARGET_HOST", "http://localhost:10000")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
PAYLOAD_DIR    = Path(__file__).parent / "payloads"

STEP_WEIGHTS = {
    # 資料蒐集
    "lang_zh": 1, "age_25": 1, "gender_male": 1, "location": 1,
    "text_2days": 1, "text_3days": 1, "text_4days": 1, "text_5days": 1,
    # 功能指令
    "text_crowd": 2, "text_recommend": 2, "text_sustain": 1, "text_rental": 1,
    "text_restaurants": 1, "text_parking": 1, "text_scenic_spots": 1,
    "text_accommodation": 1,
}

def _sign(body: bytes) -> str:
    return hmac.new(CHANNEL_SECRET.encode(), body, hashlib.sha256).hexdigest()

class LineBotUser(HttpUser):
    host = HOST
    wait_time = between(0.3, 1.0)

    _cache = {p.stem: json.loads(p.read_text("utf-8-sig"))
              for p in PAYLOAD_DIR.glob("*.json")}

    def on_start(self):
        self.uid = str(uuid.uuid4())
        self.hdr = {"Content-Type": "application/json"}

    def _post(self, name: str):
        payload = json.loads(json.dumps(self._cache[name]))
        ev = payload["events"][0]
        ev["replyToken"] = str(uuid.uuid4())
        ev["source"]["userId"] = self.uid
        ev["timestamp"] = int(time.time() * 1000)
        body = json.dumps(payload).encode()

        if CHANNEL_SECRET:
            self.hdr["X-Line-Signature"] = _sign(body)

        self.client.post("/", data=body, headers=self.hdr, name=f"POST / {name}")

    @task
    def send(self):
        name = random.choices(list(STEP_WEIGHTS), weights=STEP_WEIGHTS.values())[0]
        try:
            self._post(name)
        except Exception as exc:
            # 回報失敗但不中斷其餘任務
            self.environment.events.request.fire(
                request_type="PAYLOAD", name=f"{name}.json",
                response_time=0, response_length=0, exception=exc
            )

# ── 3. 測試結束時若需自訂統計，可在此調用 ─────────────────
try:
    from locust_db import save_stats

    @events.test_stop.add_listener
    def _save(env, **_):
        try:
            save_stats(env)
        except Exception as e:
            print(f"[locustfile] save_stats failed: {e}")
except ImportError:
    pass
