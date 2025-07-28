#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Locust script – run-once, safe CSV(;), staged user flow
────────────────────────────────────────────────────────
環境變數（可選）
  RUN_TIME_SEC   壓測秒數，預設 600 (=10 min)
  SLEEP_ON_END   保活秒數，預設 300；0 代表立刻退出
  RUN_ONCE_LOCK  鎖檔路徑，預設容器 /data/.done，本機 ./.done
"""

# ── 0. Monkey-patch User.stop ─────────────────────────────────────────────────
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

import os, csv, hashlib, hmac, json, random, time, uuid
from pathlib import Path
from gevent import spawn_later, sleep as gsleep
from locust import HttpUser, task, events, stats as _stats

# ── 1. StatsCSV patch to use semicolons ─────────────────────────────────────────
class _PatchedWriter(_stats.StatsCSVFileWriter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for fh_attr, hdr_attr, wr_attr in [
            ("stats_csv_filehandle",        "STATS_CSV_HEADERS",        "stats_csv_writer"),
            ("stats_history_csv_filehandle","STATS_HISTORY_CSV_HEADERS","stats_history_csv_writer"),
            ("failures_csv_filehandle",     "FAILURES_CSV_HEADERS",     "failures_csv_writer"),
        ]:
            fh = getattr(self, fh_attr, None)
            hdrs = getattr(self, hdr_attr, None)
            if fh and hdrs:
                fh.seek(0); fh.truncate()
                writer = csv.writer(
                    fh,
                    delimiter=";",
                    quoting=csv.QUOTE_MINIMAL,
                    lineterminator="\n"
                )
                writer.writerow(hdrs)
                setattr(self, wr_attr, writer)

_stats.StatsCSVFileWriter = _PatchedWriter

# ── 2. run-once lock & auto-stop (robust) ────────────────────────────────────────
RUN_TIME_SEC = int(os.getenv("RUN_TIME_SEC", "600"))
SLEEP_KEEP   = int(os.getenv("SLEEP_ON_END", "300"))
DEFAULT_LOCK = "/data/.done" if os.name != "nt" else ".done"
SENTINEL     = Path(os.getenv("RUN_ONCE_LOCK", DEFAULT_LOCK))

def _get_env(kw):
    return kw.get("environment") or kw.get("env")

@events.init.add_listener
def _setup(**kw):
    env = _get_env(kw)
    if not env:
        return
    env.stats.use_response_times_cache = True
    if SENTINEL.exists():
        print(f"[run-once] 偵測到 {SENTINEL}，跳過壓測")
        spawn_later(1, lambda: env.runner and env.runner.quit())

@events.test_start.add_listener
def _auto_stop(**kw):
    env = _get_env(kw)
    if env and not SENTINEL.exists():
        spawn_later(RUN_TIME_SEC, lambda: env.runner and env.runner.quit())

@events.test_stop.add_listener
def _on_stop(**kw):
    # 確保一定建立鎖檔
    SENTINEL.parent.mkdir(parents=True, exist_ok=True)
    SENTINEL.touch(exist_ok=True)
    env = _get_env(kw)
    if SLEEP_KEEP:
        print(f"[keep-alive] 容器將於 {SLEEP_KEEP}s 後退出")
        gsleep(SLEEP_KEEP)

# optional: save_stats on test_stop
try:
    from locust_db import save_stats
    @events.test_stop.add_listener
    def _save(**kw):
        env = _get_env(kw)
        if not env:
            return
        try:
            save_stats(env)
        except Exception as e:
            print(f"[locustfile] save_stats failed: {e}")
except ImportError:
    pass

# ── 3. 使用者行為定義 ───────────────────────────────────────────────────────────
HOST           = os.getenv("TARGET_HOST", "http://localhost:10000")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
PAYLOAD_DIR    = Path(__file__).parent / "payloads"

INIT_SEQ   = ["lang_zh", "age_25", "gender_male", "location"]
DAY_OPTS   = ["text_2days", "text_3days", "text_4days", "text_5days"]
POST_CMDS  = [
    "text_crowd", "text_general_recommend", "text_sustain", "text_rental",
    "text_restaurants", "text_parking", "text_scenic_spots", "text_accommodation",
]

# 預先載入所有 JSON payload
CACHE = {
    p.stem: json.loads(p.read_text("utf-8-sig"))
    for p in PAYLOAD_DIR.glob("*.json")
}

def _sign(body_bytes: bytes) -> str:
    return hmac.new(
        CHANNEL_SECRET.encode("utf-8"),
        body_bytes,
        hashlib.sha256
    ).hexdigest()

class LineBotUser(HttpUser):
    host = HOST

    def wait_time(self):
        # 初始化階段用短間隔，完成後用標準間隔
        if not getattr(self, "init_done", False):
            return random.uniform(0.5, 1.0)
        return random.uniform(5.0, 10.0)

    def on_start(self):
        self.uid        = str(uuid.uuid4())
        self.hdr        = {"Content-Type": "application/json"}
        self.stage      = 0
        self.init_done  = False

    def _post(self, name: str):
        payload = json.loads(json.dumps(CACHE[name]))  # 深拷貝
        ev = payload["events"][0]
        ev.update(
            replyToken=str(uuid.uuid4()),
            timestamp=int(time.time() * 1000),
            source={"userId": self.uid, "type": "user"},
        )
        body = json.dumps(payload).encode("utf-8")
        headers = dict(self.hdr)
        if CHANNEL_SECRET:
            headers["X-Line-Signature"] = _sign(body)
        self.client.post("/", data=body, headers=headers, name=f"POST / {name}")

    @task
    def send(self):
        try:
            # 初始階段：只執行 INIT_SEQ
            if not self.init_done:
                if self.stage < len(INIT_SEQ):
                    name = INIT_SEQ[self.stage]
                    self.stage += 1
                    self._post(name)
                    return
                else:
                    # 完成初始化後，切換標記
                    self.init_done = True

            # 初始化完成後，隨機從 DAY_OPTS 與 POST_CMDS 合併清單中選擇
            name = random.choice(DAY_OPTS + POST_CMDS)
            self._post(name)

        except Exception as exc:
            # 上報至 Locust UI
            self.environment.events.request.fire(
                request_type="PAYLOAD",
                name=f"{name}.json",
                response_time=0,
                response_length=0,
                exception=exc
            )
