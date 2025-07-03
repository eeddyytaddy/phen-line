#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Locust script  (patched for clean CSV + response-times cache)
──────────────────────────────────────────────────────────────
• 將 JSON payload 放到 ./tests/payloads/
• 在 STEP_WEIGHTS 增加 1 行 (檔名: 權重) 即可納入壓測
"""

# ── 0. 強制開啟 response-times cache + 改寫 CSV Writer ─────────────
import csv
from locust import stats as _stats

# 0-a) 根治 ValueError: StatsEntry.use_response_times_cache must be True
_stats.StatsEntry.use_response_times_cache = True

# 0-b) 將 full-history CSV 改為分號 `;` 分隔並加引號
class _PatchedWriter(_stats.StatsCSVFileWriter):
    def __init__(self, environment, base_filepath):
        super().__init__(environment, base_filepath)
        self.stats_history_file.seek(0)
        self.stats_history_file.truncate(0)
        self.stats_history_csv_writer = csv.writer(
            self.stats_history_file,
            delimiter=";",
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )
        self.stats_history_csv_writer.writerow(self.STATS_HISTORY_CSV_HEADERS)
        self.stats_history_file.flush()

_stats.StatsCSVFileWriter = _PatchedWriter  # 替換原類別

# ── 1. 其他相依套件 ────────────────────────────────────────────
import hashlib, hmac, json, os, random, time, uuid
from pathlib import Path
from locust import HttpUser, between, events, task

# ── 2. 基本參數 ───────────────────────────────────────────────
HOST           = os.getenv("TARGET_HOST", "http://localhost:10000")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
PAYLOAD_DIR    = Path(__file__).parent / "payloads"

STEP_WEIGHTS: dict[str, int] = {
    # 資料蒐集
    "lang_zh": 1, "age_25": 1, "gender_male": 1, "location": 1,
    "text_2days": 1, "text_3days": 1, "text_4days": 1, "text_5days": 1,
    # 功能指令
    "text_crowd": 2, "text_recommend": 2, "text_sustain": 1, "text_rental": 1,
    "text_restaurants": 1, "text_parking": 1, "text_scenic_spots": 1,
    "text_accommodation": 1,
}

# ── 3. 共用函式 ───────────────────────────────────────────────
def _make_signature(body: bytes) -> str:
    return hmac.new(CHANNEL_SECRET.encode(), body, hashlib.sha256).hexdigest()

# ── 4. Locust User ───────────────────────────────────────────
class LineBotUser(HttpUser):
    host = HOST
    wait_time = between(0.3, 1.0)

    _cache: dict[str, dict] = {
        p.stem: json.loads(p.read_text("utf-8-sig"))
        for p in PAYLOAD_DIR.glob("*.json")
    }

    def on_start(self):
        self.uid = str(uuid.uuid4())
        self.hdr = {"Content-Type": "application/json"}

    def _post(self, name: str):
        payload = json.loads(json.dumps(self._cache[name]))  # 深複製
        payload["events"][0]["replyToken"] = str(uuid.uuid4())
        payload["events"][0]["source"]["userId"] = self.uid
        payload["events"][0]["timestamp"] = int(time.time() * 1000)
        body = json.dumps(payload).encode("utf-8")

        if CHANNEL_SECRET:
            self.hdr["X-Line-Signature"] = _make_signature(body)

        self.client.post("/", data=body, headers=self.hdr, name=f"POST / {name}")

    @task
    def run_all_steps(self):
        name = random.choices(list(STEP_WEIGHTS), weights=STEP_WEIGHTS.values())[0]
        try:
            self._post(name)
        except Exception as exc:
            self.environment.events.request.fire(
                request_type="PAYLOAD",
                name=f"{name}.json",
                response_time=0,
                response_length=0,
                exception=exc,
            )

# ── 5. 測試結束鉤子（自訂報表，可選） ───────────────────────
from locust_db import save_stats  # 如無此模組可移除

@events.test_stop.add_listener
def _on_test_stop(env, **_):
    st = env.runner.stats.total
    print(f"\nRequests: {st.num_requests} | Failures: {st.num_failures} | P95: {st.get_response_time_percentile(0.95):.0f} ms")
    try:
        save_stats(env)
    except Exception as e:
        print(f"[locustfile] save_stats failed: {e}")
