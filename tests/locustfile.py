#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Locust script (auto-stop + safe CSV + keep-alive)
──────────────────────────────────────────────────
• JSON payload 放在 ./tests/payloads/
• STEP_WEIGHTS 調整即可新增腳本
環境變數：
  RUN_TIME_SEC   測試持續秒數 (預設 600)
  SLEEP_ON_END   測試完持續存活秒數 (預設 300；0 則立刻退出)
"""

# ── 0. 修補 Locust 內部 ────────────────────────────────────────
import os, csv
from locust import stats as _stats, events

# 0-a response-times cache（避免 ValueError）
_stats.StatsEntry.use_response_times_cache = True

# 0-b CSV writer → 分號分隔 + 引號
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

# ── 1. 自動停止 & 收尾睡眠 ─────────────────────────────────────
from gevent import spawn_later, sleep as gsleep

RUN_TIME_SEC   = int(os.getenv("RUN_TIME_SEC",   "600"))   # 10 分鐘
SLEEP_ON_END   = int(os.getenv("SLEEP_ON_END",   "300"))   # 5 分鐘

@events.test_start.add_listener
def _schedule_auto_quit(env, **_):
    def _stop():
        if env.runner:
            print(f"[auto-stop] {RUN_TIME_SEC}s 到，停止壓測")
            env.runner.quit()
    spawn_later(RUN_TIME_SEC, _stop)

@events.test_stop.add_listener
def _keep_alive(env, **_):
    if SLEEP_ON_END > 0:
        print(f"[keep-alive] 測試結束，容器將於 {SLEEP_ON_END}s 後退出")
        gsleep(SLEEP_ON_END)

# ── 2. 其餘原有邏輯（payload 壓測）───────────────────────────
import hashlib, hmac, json, random, time, uuid
from pathlib import Path
from locust import HttpUser, between, task

HOST           = os.getenv("TARGET_HOST", "http://localhost:10000")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
PAYLOAD_DIR    = Path(__file__).parent / "payloads"

STEP_WEIGHTS = {
    "lang_zh": 1, "age_25": 1, "gender_male": 1, "location": 1,
    "text_2days": 1, "text_3days": 1, "text_4days": 1, "text_5days": 1,
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
        body = json.dumps(payload).encode("utf-8")
        if CHANNEL_SECRET:
            self.hdr["X-Line-Signature"] = _sign(body)
        self.client.post("/", data=body, headers=self.hdr, name=f"POST / {name}")

    @task
    def run_all(self):
        name = random.choices(list(STEP_WEIGHTS), weights=STEP_WEIGHTS.values())[0]
        try:
            self._post(name)
        except Exception as e:
            # 回報失敗但不中斷
            self.environment.events.request.fire(
                request_type="PAYLOAD", name=f"{name}.json",
                response_time=0, response_length=0, exception=e
            )

# ── 3. 可選：自訂統計輸出 ───────────────────────────────────
try:
    from locust_db import save_stats

    @events.test_stop.add_listener
    def _save(env, **_):
        try:
            save_stats(env)
        except Exception as exc:
            print(f"[locustfile] save_stats failed: {exc}")
except ImportError:
    pass
