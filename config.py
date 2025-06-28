#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
config.py
~~~~~~~~~
專案統一設定檔：
  • CSV 與模型路徑
  • MySQL 連線資料
  • SQLite / D1 資料庫路徑
  • Cloudflare Worker URL
⚠️ 關鍵修改：讓壓測寫入 (LOCUST_DB) 與圖表讀取 (D1_BINDING) 指向同一顆檔案
"""

import os
from os import path

# ──────────────────────────────────────────────────────────────
# 1. 專案根目錄
# ──────────────────────────────────────────────────────────────
BASE_PROJECT = path.dirname(path.abspath(__file__))

# ──────────────────────────────────────────────────────────────
# 2. 執行環境：local / docker（可用 APP_ENV 切換）
# ──────────────────────────────────────────────────────────────
ENV = os.getenv("APP_ENV", "local")

if ENV == "docker":
    BASE_CSV_PATH = os.getenv(
        "BASE_CSV_PATH",
        path.join(BASE_PROJECT, "penghu_csv_file")
    )
    MYSQL_HOST = os.getenv("MYSQL_HOST", "db")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
    D1_DB_PATH = "/usr/src/app/d1_database.sqlite"        # 容器內固定路徑
else:
    BASE_CSV_PATH = os.getenv(
        "BASE_CSV_PATH",
        path.join(BASE_PROJECT, "penghu_csv_file")
    )
    MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3307))
    D1_DB_PATH = os.getenv(                           # 本機 / 雲端都優先讀環境變數
        "D1_DB_PATH",
        path.join(BASE_PROJECT, "d1_database.sqlite")
    )

# ──────────────────────────────────────────────────────────────
# 3. D1 SQL Binding  (Cloudflare) - or- SQLite fallback
#    ▶ D1_BINDING = 最終圖表 / 指標都要連的 DB
# ──────────────────────────────────────────────────────────────
D1_BINDING = os.getenv("D1_PENGHU", "") or D1_DB_PATH

# ──────────────────────────────────────────────────────────────
# 4. Locust 也寫進同一顆 → 完整統一
#    ▶ 如果外部想自訂另一檔，可個別設 LOCUST_DB
# ──────────────────────────────────────────────────────────────
LOCUST_DB = os.getenv("LOCUST_DB", D1_BINDING)

# ──────────────────────────────────────────────────────────────
# 5. Cloudflare Worker URL
# ──────────────────────────────────────────────────────────────
WORKER_URL = os.getenv(
    "WORKER_URL",
    "https://penghu-plan.eeddyytaddy.workers.dev"
)

# ──────────────────────────────────────────────────────────────
# 6. CSV 檔案路徑
# ──────────────────────────────────────────────────────────────
PLAN                  = path.join(BASE_CSV_PATH, "plan.csv")
PLAN_CSV              = PLAN
PLAN_2DAY             = path.join(BASE_CSV_PATH, "plan_2day.csv")
PLAN_3DAY             = path.join(BASE_CSV_PATH, "plan_3day.csv")
PLAN_4DAY             = path.join(BASE_CSV_PATH, "plan_4day.csv")
PLAN_5DAY             = path.join(BASE_CSV_PATH, "plan_5day.csv")
LOCATION_FILE         = path.join(BASE_CSV_PATH, "location.csv")

RECOMMEND_CSV         = path.join(BASE_CSV_PATH, "recommend.csv")
HOTEL_DATA_CSV        = path.join(BASE_CSV_PATH, "hotel_data.csv")
BEACON_INPUT_CSV      = path.join(BASE_CSV_PATH, "Beacon20220907-crowd.csv")
BEACON_OUTPUT_CSV     = path.join(BASE_CSV_PATH, "Beacon20220907-crowd-placeid10.csv")
PENGHU_ORIGINAL_CSV   = path.join(BASE_CSV_PATH, "penghu_orignal2.csv")
GENERATED_DATA_CSV    = path.join(BASE_CSV_PATH, "generated_data_updated1.csv")

SUSTAINABLE_ATTR_CSV  = path.join(BASE_CSV_PATH, "test", "Sustainable",      "locations_Attractions.csv")
NON_SUSTAINABLE_ATTR_CSV = path.join(BASE_CSV_PATH, "test", "non Sustainable", "penghu_Attractions.csv")
SUSTAINABLE_NON_ATTR_CSV = path.join(BASE_CSV_PATH, "test", "Sustainable",      "locations_non_Attractions.csv")
NON_SUSTAINABLE_NON_ATTR_CSV = path.join(BASE_CSV_PATH, "test", "non Sustainable", "penghu_non_Attractions.csv")

# ──────────────────────────────────────────────────────────────
# 7. 機器學習模型檔案
# ──────────────────────────────────────────────────────────────
MODEL_DIR                       = BASE_PROJECT
XGB_MODEL1_PATH                 = path.join(MODEL_DIR, "xgb_model1.bin")
XGB_MODEL2_PATH                 = path.join(MODEL_DIR, "xgb_model2.bin")
PHTEST_MODEL_PATH               = path.join(MODEL_DIR, "PHtest.bin")
SUSTAINABLE_MODEL_PATH          = path.join(MODEL_DIR, "sustainable_Attractions.bin")
NON_SUSTAINABLE_MODEL_PATH      = path.join(MODEL_DIR, "non_sustainable_attraction.bin")
SUSTAINABLE_NON_MODEL_PATH      = path.join(MODEL_DIR, "sustainable_non_Attractions.bin")
NON_SUSTAINABLE_NON_MODEL_PATH  = path.join(MODEL_DIR, "non_sustainable_non_Attractions.bin")

# ──────────────────────────────────────────────────────────────
# 8. MySQL 連線資訊
# ──────────────────────────────────────────────────────────────
MYSQL_USER      = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD  = os.getenv("MYSQL_PASSWORD", "nclab722")
MYSQL_DATABASE  = os.getenv("MYSQL_DATABASE", "penghu")

# End of file
