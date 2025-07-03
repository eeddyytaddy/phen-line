#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Locust script
─────────────
• 將 JSON payload 放到 ./tests/payloads/ 目錄
• 在 STEP_WEIGHTS 增加一行 (key=檔名, value=權重) 即可納入壓測
"""

import hashlib, hmac, json, os, random, time, uuid, csv
from pathlib import Path
from locust import HttpUser, between, events, task, stats

# ── 0. 參數設定 ───────────────────────────────────────────────
HOST           = os.getenv("TARGET_HOST", "http://localhost:10000")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")   # 留空 ⇒ 不簽章
PAYLOAD_DIR    = Path(__file__).parent / "payloads"

# payload → 權重（數字愈大出現機率愈高）
STEP_WEIGHTS: dict[str, int] = {
    # phase 0：使用者資料蒐集
    "lang_zh": 1, "age_25": 1, "gender_male": 1, "location": 1,
    "text_2days": 1, "text_3days": 1, "text_4days": 1, "text_5days": 1,
    # phase 1：功能指令
    "text_crowd": 2, "text_recommend": 2, "text_sustain": 1, "text_rental": 1,
    "text_restaurants": 1, "text_parking": 1, "text_scenic_spots": 1,
    "text_accommodation": 1,
}

# ── 1-a. 開啟 response-times cache（寫 full-history 需用） ─────────
@events.init.add_listener
def enable_response_times_cache(environment, **_):
    environment.stats.use_response_times_cache = True

# ── 1-b. 補丁：把 full-history CSV 改成分號分隔＋加引號 ───────────
@events.init.add_listener
def patch_csv_writer(environment, **_):
    """
    Locust ≤2.27 在 full-history CSV 沒有為文字欄位加引號，且強制逗號分隔，
    容易造成欄位數錯亂。猴子補丁 StatsCSVFileWriter，使其：
      • delimiter 改為 ';'
      • lineterminator 改 '\n'
      • quoting = csv.QUOTE_MINIMAL
    """
    OrigWriter = stats.StatsCSVFileWriter

    class PatchedWriter(OrigWriter):
        def __init__(self, environment, base_filepath):
            super().__init__(environment, base_filepath)
            # 重新初始化 writer
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

    stats.StatsCSVFileWriter = PatchedWriter  # 注入補丁

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

    # 送出指定 payload
    def _post(self, name: str):
        if name not in self._cache:
            raise ValueError(f"payload '{name}.json' not found")

        payload = json.loads(json.dumps(self._cache[name]))  # 深複製
        payload["events"][0]["replyToken"] = str(uuid.uuid4())
        payload["events"][0]["source"]["userId"] = self.uid
        payload["events"][0]["timestamp"] = int(time.time() * 1000)
        body = json.dumps(payload).encode("utf-8")

        if CHANNEL_SECRET:
            self.hdr["X-Line-Signature"] = _make_signature(body)

        self.client.post("/", data=body, headers=self.hdr, name=f"POST / {name}")

    # 單一 task：每次隨機挑一個 payload
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

# ── 4. 測試結束鉤子 → 自訂報表 ───────────────────────────────
from locust_db import save_stats  # 若不需要可移除

@events.test_stop.add_listener
def on_test_stop(environment, **_):
    stats_total = environment.runner.stats.total
    print(
        f"\nRequests : {stats_total.num_requests}  |  "
        f"Failures : {stats_total.num_failures}  |  "
        f"P95 : {stats_total.get_response_time_percentile(0.95):.0f} ms"
    )
    try:
        save_stats(environment)
    except Exception as e:
        print(f"[locustfile] save_stats failed: {e}")
