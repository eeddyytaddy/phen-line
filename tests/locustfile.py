#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Locust script  – run-once, safe CSV, keep-alive
───────────────────────────────────────────────
環境變數（可選）
  RUN_TIME_SEC   壓測秒數，預設 600 (=10 min)
  SLEEP_ON_END   壓測完/略過後保活秒數，預設 300；0 表立即退出
  RUN_ONCE_LOCK  鎖檔路徑，預設容器 /data/.done，本機 ./.done
"""

# ── 0. Monkey-patch User.stop ─────────────────────────────────────────────
# 避免「unexpected state: stopping」例外
from locust.user.users import User as _User
_orig_stop = _User.stop
def _safe_stop(self, force=False):
    try:
        return _orig_stop(self, force=force)
    except Exception as e:
        if "unexpected state" in str(e):
            return
        raise
_User.stop = _safe_stop

# ── 1. 內部補丁：StatsCSVFileWriter 改用分號 & 任意參數 ────────────────
import os, csv, sys
from pathlib import Path
from gevent import spawn_later, sleep as gsleep
from locust import stats as _stats, events

class _PatchedWriter(_stats.StatsCSVFileWriter):
    def __init__(self, *args, **kwargs):
        super(_PatchedWriter, self).__init__(*args, **kwargs)  # 相容新版簽名
        fh = self.stats_history_csv_filehandle                 # 取檔案 handle
        fh.seek(0); fh.truncate()
        self.stats_history_csv_writer = csv.writer(
            fh, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\n"
        )
        self.stats_history_csv_writer.writerow(self.stats_history_csv_columns)
        fh.flush()
_stats.StatsCSVFileWriter = _PatchedWriter

# ── 2. 參數與一次鎖 ────────────────────────────────────────────────
RUN_TIME_SEC = int(os.getenv("RUN_TIME_SEC", "600"))
SLEEP_KEEP   = int(os.getenv("SLEEP_ON_END", "300"))

DEFAULT_LOCK = "/data/.done" if os.name != "nt" else ".done"
SENTINEL     = Path(os.getenv("RUN_ONCE_LOCK", DEFAULT_LOCK))

@events.init.add_listener
def _setup(environment, **_):
    environment.stats.use_response_times_cache = True
    if SENTINEL.exists():                      # 已跑過 → 立即退出
        print(f"[run-once] 偵測到 {SENTINEL}，跳過壓測。")
        spawn_later(1, lambda: environment.runner and environment.runner.quit())

@events.test_start.add_listener
def _auto_stop(environment, **_):
    if not SENTINEL.exists():                  # 首次 → 排程自動停止
        spawn_later(RUN_TIME_SEC, lambda: environment.runner and environment.runner.quit())

@events.test_stop.add_listener
def _on_stop(environment, **_):
    # 建立鎖檔（若父資料夾不存在就先建立）
    SENTINEL.parent.mkdir(parents=True, exist_ok=True)
    if not SENTINEL.exists():
        SENTINEL.touch()
        print(f"[run-once] 壓測完成，已建立 {SENTINEL}")
    # 依設定保活
    if SLEEP_KEEP > 0:
        print(f"[keep-alive] 容器將於 {SLEEP_KEEP}s 後退出")
        gsleep(SLEEP_KEEP)

# ── 3. 壓測邏輯 ─────────────────────────────────────────────────────
import hashlib, hmac, json, random, time, uuid
from locust import HttpUser, between, task

HOST           = os.getenv("TARGET_HOST", "http://localhost:10000")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
PAYLOAD_DIR    = Path(__file__).parent / "payloads"

STEP_WEIGHTS = {
    "lang_zh": 1, "age_25": 1, "gender_male": 1, "location": 1,
    "text_2days": 1, "text_3days": 1, "text_4days": 1, "text_5days": 1,
    "text_crowd": 1, "text_general_recommend": 1, "text_sustain": 1, "text_rental": 1,
    "text_restaurants": 1, "text_parking": 1, "text_scenic_spots": 1,
    "text_accommodation": 1,
}

def _sign(b: bytes) -> str:
    return hmac.new(CHANNEL_SECRET.encode(), b, hashlib.sha256).hexdigest()

class LineBotUser(HttpUser):
    host = HOST
    wait_time = between(0.3, 1.0)
    _cache = {p.stem: json.loads(p.read_text("utf-8-sig"))
              for p in PAYLOAD_DIR.glob("*.json")}

    def on_start(self):
        self.uid = str(uuid.uuid4())
        self.hdr = {"Content-Type": "application/json"}

    def _post(self, name):
        payload = json.loads(json.dumps(self._cache[name]))
        ev = payload["events"][0]
        ev.update(
            replyToken=str(uuid.uuid4()),
            timestamp=int(time.time() * 1000),
            source={"userId": self.uid, "type": "user"},
        )
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
            self.environment.events.request.fire(
                request_type="PAYLOAD", name=f"{name}.json",
                response_time=0, response_length=0, exception=exc
            )

# ── 4. (可選) 自訂統計存檔 ─────────────────────────────────────
try:
    from locust_db import save_stats

    @events.test_stop.add_listener
    def _save(environment, **_):
        try:
            save_stats(environment)
        except Exception as e:
            print(f"[locustfile] save_stats failed: {e}")
except ImportError:
    pass
