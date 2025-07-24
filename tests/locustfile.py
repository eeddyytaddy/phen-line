#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Locust script – run-once, safe CSV(;), keep-alive
──────────────────────────────────────────────────
環境變數（可選）
  RUN_TIME_SEC   壓測秒數，預設 600 (=10 min)
  SLEEP_ON_END   保活秒數，預設 300；0 代表立刻退出
  RUN_ONCE_LOCK  鎖檔路徑，預設容器 /data/.done，本機 ./.done
"""

# ╭─ 0. Monkey-patch：User.stop 忽略 stopping 狀態例外 ───────────╮
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
# ╰──────────────────────────────────────────────────────────────╯

# ╭─ 1. 內部補丁：StatsCSVFileWriter 全部改用分號 ────────────────╮
import os, csv
from pathlib import Path
from gevent import spawn_later, sleep as gsleep
from locust import stats as _stats, events

class _PatchedWriter(_stats.StatsCSVFileWriter):
    """
    1. 兼容新版多參數簽名 (*args, **kwargs)
    2. stats / history / failures 三種 CSV 均改 delimiter=';'
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)  # 先讓原生邏輯開好檔案

        # (handle attr, header attr, writer attr) 組
        targets = [
            ("stats_csv_filehandle",        "STATS_CSV_HEADERS",        "stats_csv_writer"),
            ("stats_history_csv_filehandle","STATS_HISTORY_CSV_HEADERS","stats_history_csv_writer"),
            ("failures_csv_filehandle",     "FAILURES_CSV_HEADERS",     "failures_csv_writer"),
        ]
        for fh_attr, hdr_attr, wr_attr in targets:
            fh   = getattr(self, fh_attr, None)
            hdrs = getattr(self, hdr_attr, None)
            if fh is None or hdrs is None:
                continue  # 某些版本可能沒 failures

            fh.seek(0); fh.truncate()      # 清空逗號版內容
            writer = csv.writer(
                fh, delimiter=";",
                quoting=csv.QUOTE_MINIMAL,
                lineterminator="\n",
            )
            writer.writerow(hdrs)
            setattr(self, wr_attr, writer)  # 用新的 writer 取代

_stats.StatsCSVFileWriter = _PatchedWriter
# ╰──────────────────────────────────────────────────────────────╯

# ╭─ 2. 參數與 run-once 鎖 ────────────────────────────────────────╮
RUN_TIME_SEC = int(os.getenv("RUN_TIME_SEC", "600"))
SLEEP_KEEP   = int(os.getenv("SLEEP_ON_END", "300"))
DEFAULT_LOCK = "/data/.done" if os.name != "nt" else ".done"
SENTINEL     = Path(os.getenv("RUN_ONCE_LOCK", DEFAULT_LOCK))

@events.init.add_listener
def _setup(environment, **_):
    environment.stats.use_response_times_cache = True
    if SENTINEL.exists():
        print(f"[run-once] 偵測到 {SENTINEL}，跳過壓測。")
        spawn_later(1, lambda: environment.runner and environment.runner.quit())

@events.test_start.add_listener
def _auto_stop(environment, **_):
    if not SENTINEL.exists():
        spawn_later(RUN_TIME_SEC, lambda: environment.runner and environment.runner.quit())

@events.test_stop.add_listener
def _on_stop(environment, **_):
    SENTINEL.parent.mkdir(parents=True, exist_ok=True)
    if not SENTINEL.exists():
        SENTINEL.touch()
        print(f"[run-once] 壓測完成，已建立 {SENTINEL}")
    if SLEEP_KEEP > 0:
        print(f"[keep-alive] 容器將於 {SLEEP_KEEP}s 後退出")
        gsleep(SLEEP_KEEP)
# ╰──────────────────────────────────────────────────────────────╯

# ╭─ 3. 壓測使用者邏輯（LINE Bot 範例）────────────────────────────╮
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

    def _post(self, name: str):
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
# ╰──────────────────────────────────────────────────────────────╯

# ╭─ 4. (可選) 自訂統計存檔 ───────────────────────────────────────╮
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
# ╰──────────────────────────────────────────────────────────────╯
