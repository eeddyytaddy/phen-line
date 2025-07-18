#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
locustfile.py ―― 先完成 5 步資料收集，之後隨機呼叫其他指令
────────────────────────────────────────────
環境變數（可選）：
  TARGET_HOST           目標主機，預設 http://localhost:10000
  LINE_CHANNEL_SECRET   LINE 簽章金鑰；不需要可留空
  PAYLOAD_DIR           JSON 樣本目錄，預設 ./payloads
  RUN_TIME_SEC          壓測秒數，預設 600 (=10 分鐘)
  SLEEP_ON_END          測完後保活秒數，預設 300；0 → 立即退出
  FUNC_RT_CSV           CSV 路徑（如需自訂）
"""

import os, json, random, time, uuid, hmac, hashlib
from pathlib import Path
from gevent import spawn_later, sleep as gsleep
from locust import HttpUser, TaskSet, task, between, events, stats as _stats
import csv, sys

# ──────────────────────────────────────────
# 0. 分號 CSV patch
# ──────────────────────────────────────────
class _PatchedWriter(_stats.StatsCSVFileWriter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        file_attr   = "stats_history_file"    if hasattr(self, "stats_history_file")    else "_stats_history_file"
        writer_attr = "stats_history_csv_writer" if hasattr(self, "stats_history_csv_writer") else "_stats_history_csv_writer"
        stats_file = getattr(self, file_attr, None)
        if not stats_file:
            return
        stats_file.seek(0); stats_file.truncate(0)
        csv_writer = csv.writer(stats_file, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        setattr(self, writer_attr, csv_writer)
        hdr = getattr(self, "STATS_HISTORY_CSV_HEADERS", None)
        if hdr:
            csv_writer.writerow(hdr)
        stats_file.flush()
_stats.StatsCSVFileWriter = _PatchedWriter

# ──────────────────────────────────────────
# 1. run-once & keep-alive
# ──────────────────────────────────────────
RUN_TIME_SEC = int(os.getenv("RUN_TIME_SEC", "600"))
SLEEP_KEEP   = int(os.getenv("SLEEP_ON_END", "300"))
SENTINEL     = Path("/data/.done")

@events.test_start.add_listener
def on_test_start(env, **kw):
    env.stats.use_response_times_cache = True
    if SENTINEL.exists():
        spawn_later(1, lambda: env.runner and env.runner.quit())
    else:
        spawn_later(RUN_TIME_SEC, lambda: env.runner and env.runner.quit())

@events.test_stop.add_listener
def on_test_stop(env, **kw):
    if not SENTINEL.exists():
        SENTINEL.touch()
    if SLEEP_KEEP > 0:
        gsleep(SLEEP_KEEP)

# ──────────────────────────────────────────
# 2. 壓測邏輯：先 5 步收集 → 其餘隨機
# ──────────────────────────────────────────
TARGET_HOST    = os.getenv("TARGET_HOST", "http://localhost:10000")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
PAYLOAD_DIR    = Path(os.getenv("PAYLOAD_DIR", Path(__file__).parent / "payloads"))

# 快取所有 payload JSON
_PAYLOAD = {p.stem: json.loads(p.read_text("utf-8-sig")) for p in PAYLOAD_DIR.glob("*.json")}

# 定義步驟
COLLECT_STEPS = ["lang_zh","age_25","gender_male","location"]
DAY_STEPS     = ["text_2days","text_3days","text_4days","text_5days"]
# 後續隨機池 = 所有 payload 扣除收集步驟
ALL = set(_PAYLOAD.keys())
POST_COLLECT = list(ALL - set(COLLECT_STEPS) - set(DAY_STEPS))

def _sign(body: bytes) -> str:
    return hmac.new(CHANNEL_SECRET.encode(), body, hashlib.sha256).hexdigest()

class UserBehavior(TaskSet):
    def on_start(self):
        # 初始化收集流程
        self.collected   = False
        self.uid         = str(uuid.uuid4())
        self.hdr         = {"Content-Type": "application/json"}
        self.steps       = COLLECT_STEPS + [random.choice(DAY_STEPS)]
        self.collect_idx = 0

    @task
    def step_or_random(self):
        if not self.collected:
            name = self.steps[self.collect_idx]
            self._do(name)
            self.collect_idx += 1
            if self.collect_idx >= len(self.steps):
                self.collected = True
        else:
            name = random.choice(POST_COLLECT)
            self._do(name)

    def _do(self, name):
        # 準備 body
        payload = json.loads(json.dumps(_PAYLOAD[name]))
        ev = payload["events"][0]
        ev.update(
            replyToken=str(uuid.uuid4()),
            timestamp =int(time.time()*1000),
            source    ={"userId":self.uid,"type":"user"}
        )
        body = json.dumps(payload).encode()
        if CHANNEL_SECRET:
            self.hdr["X-Line-Signature"] = _sign(body)
        # 發送
        self.client.post("/", data=body, headers=self.hdr, name=f"POST / {name}")

class LineBotUser(HttpUser):
    host      = TARGET_HOST
    wait_time = between(0.2, 1)
    tasks     = [UserBehavior]
