# app.py
import os
import io
import json
import csv
import sqlite3
import threading
from datetime import datetime as dt
from random import randrange
from collections import Counter
from zh2en import TEXTS as I18N, to_en ,ZH2EN
from flask import Flask, request, jsonify, send_file
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    TextSendMessage, ImageSendMessage, StickerSendMessage,
    TemplateSendMessage, ConfirmTemplate, MessageAction,
    ButtonsTemplate, URIAction, QuickReply, QuickReplyButton
)
from linebot.models.events import PostbackEvent
from shared import (
    user_language, user_stage,
    user_age, user_gender, user_trip_days,
    user_preparing, user_plan_ready
)
# Matplotlib 無頭模式
import matplotlib
import urllib.parse
from shared import user_location
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.font_manager as fm
from matplotlib.patches import Patch
# 1. 先指定 font.family 為 'sans-serif'
plt.rcParams['font.family'] = 'sans-serif'
from linebot.exceptions import LineBotApiError
# 2. 把常見的 CJK 與預設字體都加到 sans-serif 清單裡
plt.rcParams['font.sans-serif'] = [
    'Source Han Sans TC',      # Adobe 版名，有安裝時可用
    'Noto Sans CJK TC',        # 系統安裝的 Noto
    'Noto Sans CJK JP',
    'Noto Sans CJK KR',
    'DejaVu Sans',             # fallback
]

# 3. 如果有專案 fonts 資料夾下的 OTF，就載入並插到最前面
font_path = os.path.join(os.path.dirname(__file__), "fonts", "SourceHanSansTC-Regular.otf")
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    prop = fm.FontProperties(fname=font_path)
    plt.rcParams['font.sans-serif'].insert(0, prop.get_name())
if os.path.exists(font_path):
    try:
        fm.fontManager.addfont(font_path)
        prop = fm.FontProperties(fname=font_path)
        plt.rcParams["font.family"] = prop.get_name()
        print(f"✅ 已使用自訂字體: {prop.get_name()}")
    except Exception as e:
        print(f"⚠️ 載入自訂字體失敗 ({e})，改用系統字體")
        if os.getenv("APP_ENV") == "docker":
            plt.rcParams["font.family"] = "Noto Sans CJK TC"
        else:
            plt.rcParams["font.family"] = "Microsoft JhengHei"
else:
    print("ℹ️ 未找到自訂字體，使用系統字體")
    if os.getenv("APP_ENV") == "docker":
        plt.rcParams["font.family"] = "Noto Sans CJK TC"
    else:
        plt.rcParams["font.family"] = "Microsoft JhengHei"

# 資料處理
import pandas as pd
import numpy as np
import requests
import googlemaps
from shared import user_age, user_gender
# 自製模組
from timer import measure_time
from report_runtime import fetch_data
from config import (
    MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE,
    PLAN_CSV, PLAN_2DAY, PLAN_3DAY, PLAN_4DAY, PLAN_5DAY,
    LOCATION_FILE, RECOMMEND_CSV
)
import re
import unicodedata
import XGBOOST_predicted
import ML
import Search
import Now_weather
import Filter
import FlexMessage
import Googlemap_function
import get_location
import plan_location
import PH_Attractions
from plan2d1 import csv_up
from collections import Counter, defaultdict
from dotenv import load_dotenv
import os
from flask import Flask, request, jsonify, send_file
from prometheus_client import make_wsgi_app
from werkzeug.middleware.dispatcher import DispatcherMiddleware 

import routes_metrics 
import metrics
from resource_monitor import init_app

load_dotenv()   # 這行會去根目錄找 .env，並把變數載入 os.environ
# ─────────────── Flask App ───────────────
app = Flask(__name__)

init_app(app, interval=5)   # 只需這一行
metrics.init_metrics(app)  
import routes_metrics              # 不會產生循環
routes_metrics.register_png_routes(app)

# LINE Bot 設定
ACCESS_TOKEN   = os.getenv("LINE_ACCESS_TOKEN",   "your_line_access_token_here")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "your_line_channel_secret_here")
line_bot_api   = LineBotApi(ACCESS_TOKEN)
handler        = WebhookHandler(CHANNEL_SECRET)
# 常數
#PHP_ngrok = "https://flask-service2.peterlinebot.ip-ddns.com"
PHP_NGROK       = "https://penghu-linebot.onrender.com"
GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSeT7kHB3bsE7rmxqJdzG42XfSS9ewNBBZPVH3xxunpYVcyDag/viewform?usp=header"
GOOGLE_API_KEY  = os.getenv("GOOGLE_MAPS_API_KEY")
# ─────────────── 每-user 語系設定 & 其他全域狀態 ───────────────
from shared import user_language, user_stage


approveLangRespond  = False
approveAgeRespond   = False
approveGender       = False
approveDaysRespond  = False
# ─────────────── 多語小助手 ───────────────
def _t(key: str, lang: str) -> str:
    """
    從 I18N 裡撈對應語系字串；若找不到，回傳 key 本身。
    lang: 'zh' or 'en'
    """
    return I18N.get(lang, I18N['zh']).get(key, key)

def _get_lang(uid: str) -> str:
    """取得該 user 的語系設定"""
    return user_language.get(uid, 'zh')

# ─────────────── LINE 安全封裝 ───────────────
used_reply_tokens = set()

def safe_reply(token, msgs, uid=None):
    """
    安全的 reply 函式，避免重複使用 reply token。
    若 reply_message 回傳 Invalid reply token，且有傳入 uid，則改以 safe_push 送出。
    其他例外皆只記錄，不再二次嘗試 line_bot_api.push_message。
    """
    if not token:
        print("Warning: Reply token is None or empty")
        return

    # 避免同一個 token 重複用
    if token in used_reply_tokens:
        print(f"Warning: Reply token {token} already used, skipping reply")
        return

    # 確保 msgs 是 list
    if not isinstance(msgs, list):
        msgs = [msgs]

    try:
        # 嘗試 reply
        line_bot_api.reply_message(token, msgs)
        used_reply_tokens.add(token)
        print(f"Reply sent successfully with token: {token}")
    except LineBotApiError as e:
        # 取得錯誤細節
        status_code = getattr(e, "status_code", None)
        request_id  = getattr(e, "request_id",  None)
        error_message = e.error.message if hasattr(e, "error") and e.error else str(e)
        print(f"safe_reply error: status_code={status_code}, request_id={request_id}, message={error_message}")
        # 標記 token 已使用，避免重複
        used_reply_tokens.add(token)

        # 只有在「Invalid reply token」時，才改用 push
        if uid and "Invalid reply token" in error_message:
            print(f"Reply token {token} 無效或過期，改用 safe_push({uid})")
            safe_push(uid, msgs)
    except Exception as e:
        # 其它非 LineBotApiError
        print(f"safe_reply unexpected error: {e}")


from linebot.exceptions import LineBotApiError
from linebot.models.send_messages import SendMessage
import json

def safe_push(uid, msgs):
    """
    1) 確保 msgs 是 list
    2) 用 get_profile 驗證，404 → 直接 abort
    3) 分批，每 batch 最多 5 則、印出 payload
    4) 嘗試 push、失敗時印 status_code、request_id、message
    """
    if not isinstance(msgs, list):
        msgs = [msgs]

    # 驗證用戶為好友的唯一方式
    try:
        profile = line_bot_api.get_profile(uid)
        print(f"User profile ok: {profile.display_name} ({uid})")
    except LineBotApiError as e:
        status = e.status_code
        msg    = e.error.message if e.error else str(e)
        if status == 404:
            # 用戶沒加好友，推播一定會失敗，直接跳過
            print(f"safe_push aborted: user {uid} not following (404)")
            return
        else:
            print(f"safe_push get_profile error: status_code={status}, message={msg}")
            return

    # 切 batch、印 payload、呼 push
    batches = [msgs[i:i+5] for i in range(0, len(msgs), 5)]
    for idx, batch in enumerate(batches,1):
        payloads = []
        for m in batch:
            if isinstance(m, SendMessage):
                pd = m.as_json_dict()
                pd.pop("quickReply", None)
                payloads.append(pd)
            else:
                payloads.append(str(m))
        print(f"[Batch {idx}/{len(batches)}] payload: {json.dumps(payloads, ensure_ascii=False)}")

        try:
            line_bot_api.push_message(uid, batch)
            print(f"[Batch {idx}] push ok ({len(batch)} msgs)")
        except LineBotApiError as e:
            print(f"[Batch {idx}] push error: status_code={e.status_code}, request_id={e.request_id}, message={e.error.message}")
        except Exception as e:
            print(f"[Batch {idx}] unexpected error: {e}")

# ─────────────── 背景行程規劃 Thread ───────────────
def _background_planning(option, reply_token, user_id):
    """背景行程規劃，使用 push 而非 reply"""
    try:
        process_travel_planning(option, reply_token, user_id)
        user_plan_ready[user_id] = True
        
        # 規劃完成後推送通知
        lang = _get_lang(user_id)
        safe_push(user_id, TextSendMessage(text=_t("planning_completed", lang)))
        
    except Exception as e:
        print(f"Background planning failed: {e}")
        lang = _get_lang(user_id)
        safe_push(user_id, TextSendMessage(text=_t("planning_failed", lang)))
    finally:
        user_preparing[user_id] = False
# ========== 以下為行程／人氣／推薦等核心函式 ==========
# （完整邏輯保持不變，只把 TEXTS[...] → _t('key')，
#   中文 Label → to_en(...) if language_1=='en' else 原文）

def load_historical_avg_crowd(csv_path="daily_crowd_stats.csv"):
    """
    讀取 daily_crowd_stats.csv，回傳 {place: avg_count} 的 dict
    """
    hist_df = pd.read_csv(csv_path, encoding="utf-8-sig")
    avg_crowd = (
        hist_df
        .groupby("place")["count"]
        .mean()
        .round()
        .astype(int)
        .to_dict()
    )
    return avg_crowd

import requests
from datetime import datetime as dt
from timer import measure_time

@measure_time
def get_current_popularity(place_id):
    """
    以 Google Maps Python 客戶端 + Place Details API 取今日即時熱度 (0–100)。

    1) 若 place_id 是空字串，先用 find_place 拿 place_id
    2) 呼叫 Place Details，只要 populartimes 欄位
    3) 轉換星期索引：Python Mon=0→Google Mon=1
    4) 找到對應 day["name"] 再取當前小時的 data
    5) 全面錯誤保護，任何異常皆回傳 0
    """
    # 0. 建立 Google Maps client
    try:
        gmaps = googlemaps.Client(key=GOOGLE_API_KEY)
    except Exception:
        return 0

    # 1. 如果 place_id 不在，就先用 find_place 查一次
    if not place_id:
        try:
            res = gmaps.find_place(
                input=place_id or "",           # 空字串也要傳，但 gmaps 會回錯
                input_type="textquery",
                fields=["place_id"]
            )
            candidates = res.get("candidates", [])
            if candidates:
                place_id = candidates[0].get("place_id", "")
        except Exception:
            return 0

        if not place_id:
            return 0

    # 2. 呼叫 Place Details API 拿 populartimes
    details_url = (
        "https://maps.googleapis.com/maps/api/place/details/json"
        f"?place_id={place_id}"
        "&fields=populartimes"
        f"&key={GOOGLE_API_KEY}"
    )
    try:
        resp = requests.get(details_url, timeout=5)
        resp.raise_for_status()
        res_json = resp.json()
    except Exception:
        return 0

    pop_times = res_json.get("result", {}).get("populartimes")
    if not isinstance(pop_times, list) or not pop_times:
        return 0

    # 3. 計算今天的 weekday index
    # Python weekday(): Mon=0…Sun=6 → Google: Sun=0…Sat=6
    try:
        py_wd = dt.now().weekday()
        google_wd = (py_wd + 1) % 7
    except Exception:
        return 0

    # 4. 找到當天的 data array
    data_array = None
    for day_obj in pop_times:
        if day_obj.get("name") == google_wd:
            data_array = day_obj.get("data")
            break

    # 5. 取當前小時的熱度
    if isinstance(data_array, list):
        hour = dt.now().hour
        if 0 <= hour < len(data_array):
            try:
                val = data_array[hour]
                return int(val) if isinstance(val, (int, float, str)) else 0
            except Exception:
                return 0

    return 0


@measure_time
def update_plan_csv_with_populartimes(plan_csv_file, user_id, crowd_source="historical"):
    """
    在行程 CSV 加入 place_id、crowd（歷史或即時）、distance_km，
    並依距離、人潮排序，重設 crowd_rank。
    並把 UserID/MemID 欄位值改成該使用者的 user_id。
    讀取 shared.user_location 作為使用者定位。
    """
    # 0. 歷史人潮
    if crowd_source == "historical":
        avg_crowd = load_historical_avg_crowd()

    # 1. 取得使用者位置
    loc = user_location.get(user_id)
    if not loc:
        raise RuntimeError(f"No location for user {user_id}")
    user_lat, user_lng = loc
    user_loc = f"{user_lat},{user_lng}"

    # 2. 讀取並初始化 DataFrame
    df = pd.read_csv(plan_csv_file, encoding="utf-8-sig")
    for col, dv in [("place_id", ""), ("crowd", 0), ("distance_km", 0.0), ("crowd_rank", 0)]:
        if col not in df.columns:
            df[col] = dv

    # 3. 建立 Google Maps Client
    gmaps = googlemaps.Client(key=GOOGLE_API_KEY)

    # 4. 逐筆處理 place_id、人潮、距離
    for idx, row in df.iterrows():
        place = row["設置點"]
        # (a) 查 place_id
        try:
            res = gmaps.find_place(
                input=place,
                input_type="textquery",
                fields=["place_id"]
            )
            pid = res.get("candidates", [{}])[0].get("place_id", "")
        except:
            pid = ""
        df.at[idx, "place_id"] = pid

        # (b) 套用人潮
        if crowd_source == "historical":
            df.at[idx, "crowd"] = avg_crowd.get(place, 0)
        else:
            df.at[idx, "crowd"] = get_current_popularity(pid)

        # (c) 計算距離
        try:
            matrix = gmaps.distance_matrix(
                origins=[user_loc],
                destinations=[f"place_id:{pid}"],
                mode="driving",
                units="metric"
            )
            elem = matrix["rows"][0]["elements"][0]
            if elem.get("status") == "OK":
                df.at[idx, "distance_km"] = round(elem["distance"]["value"] / 1000, 3)
            else:
                df.at[idx, "distance_km"] = 0.0
        except:
            df.at[idx, "distance_km"] = 0.0

    # 5. 排序 & 重新編排 crowd_rank
    df.sort_values(by=["distance_km", "crowd"], ascending=[True, True], inplace=True)
    df["crowd_rank"] = range(1, len(df) + 1)

    # 5.1 覆寫 UserID/MemID 欄位為傳入的 user_id
    if "UserID/MemID" in df.columns:
        df["UserID/MemID"] = user_id

    # 6. 寫回 CSV
    df.to_csv(plan_csv_file, index=False, encoding="utf-8-sig")




# === Part 1 END ===

# ---------- app.py  ※ Part 2 / 4  ----------------------------------
# ---- 1) XGBoost 排序 (Machine Learning) ----
@measure_time
def run_ml_sort(option, reply_token, user_id, df_plan):
    """
    以 XGBoost 依性別、年齡做排序，回傳 userID list
    """
    # 1) 取出原始文字性別，並轉成數值
    raw_gender = user_gender.get(user_id, "")
    gender = FlexMessage.classify_gender(raw_gender)  # 0=男, 1=女, 2=其他

    # 2) 取年齡
    age = user_age.get(user_id, 30)

    # 3) 印出 debug 訊息並呼叫 XGBoost
    #print(f"run_ml_sort: gender={gender}, age={age}, df_plan.dtypes={df_plan.dtypes}")
    return ML.XGboost_plan(df_plan, gender, age)



# ---- 2) 景點過濾 (Attraction Filtering) ----
@measure_time
def run_filter(option, reply_token, user_id, csv_path, userID):
    """
    根據需求過濾景點（例如距離、人潮…）
    """
    Filter.filter(csv_path, userID)


# ---- 3) 景點重排名 (Attraction Ranking) ----
@measure_time
def run_ranking(option, reply_token, user_id, plan_csv):
    """
    根據即時人潮和距離再對行程排序，並寫回 CSV
    """
    update_plan_csv_with_populartimes(plan_csv, user_id, crowd_source="realtime")


# ---- 4) 上傳資料 (Data to Database) ----
@measure_time
def run_upload(option, reply_token, user_id):
    """
    把最終 CSV 上傳到遠端 PHP 或其他服務
    """
    csv_up()


# ---- 串接主流程 ----
@measure_time
def process_travel_planning(option, reply_token, user_id):
    """
    拆成四段：ML排序 → 景點過濾 → 重排名 → 上傳，
    並在每一步發生錯誤時回報，最後標記完成狀態。
    """
    # 0. 前置資料檢查
    if user_gender.get(user_id) is None or user_age.get(user_id) is None:
        lang = _get_lang(user_id)
        safe_reply(
            reply_token,
            TextSendMessage(text=_t('collect_info', lang)),
            user_id
        )
        user_preparing[user_id] = False
        return

    # 1. 讀入對應天數的行程 CSV
    csv_map = {
        "兩天一夜": PLAN_2DAY,
        "三天兩夜": PLAN_3DAY,
        "四天三夜": PLAN_4DAY,
        "五天四夜": PLAN_5DAY
    }
    csv_path = csv_map.get(option, PLAN_2DAY)
    try:
        df_plan = pd.read_csv(csv_path, encoding="utf-8-sig")
    except Exception as e:
        print("read CSV error:", e)
        lang = _get_lang(user_id)
        safe_push(user_id, TextSendMessage(text=_t('data_fetch_failed', lang)))
        user_preparing[user_id] = False
        return

    # 2. 機器學習排序
    try:
        sorted_user_list = run_ml_sort(option, reply_token, user_id, df_plan)
    except Exception as e:
        print("XGboost_plan error:", e)
        lang = _get_lang(user_id)
        safe_push(user_id, TextSendMessage(text=_t('data_fetch_failed', lang)))
        user_preparing[user_id] = False
        return

    # 3. 景點過濾
    try:
        run_filter(option, reply_token, user_id, csv_path, sorted_user_list)
    except Exception as e:
        print("filter error:", e)
        lang = _get_lang(user_id)
        safe_push(user_id, TextSendMessage(text=_t('data_fetch_failed', lang)))
        user_preparing[user_id] = False
        return

    # 4. 重排名（加入即時人潮與距離）
    try:
        run_ranking(option, reply_token, user_id, PLAN_CSV)
    except Exception as e:
        print("ranking error:", e)
        lang = _get_lang(user_id)
        safe_push(user_id, TextSendMessage(text=_t('data_fetch_failed', lang)))
        user_preparing[user_id] = False
        return

    # 5. 上傳最終結果
    try:
        run_upload(option, reply_token, user_id)
    except Exception as e:
        print("upload error:", e)
        lang = _get_lang(user_id)
        safe_push(user_id, TextSendMessage(text=_t('data_fetch_failed', lang)))
        user_preparing[user_id] = False
        return

    # 6. 標記該使用者的規劃已完成
    user_plan_ready[user_id] = True
    user_preparing[user_id]  = False

    # 可選）如需立即推送結果給使用者，取消下行註解：
    # safe_push(user_id, FlexMessage.show_plan(PLAN_CSV))



@measure_time
def people_high5(tk, uid):
    """回傳目前時段最壅擠前 5 名 (list, text)"""
    try:
        df = pd.read_csv("daily_crowd_stats.csv", encoding="utf-8-sig")
        hr = dt.now().hour
        top5 = (df[df["hour"] == hr]
                .sort_values("count", ascending=False)
                .head(5))
        msg = "\n".join(f"{i+1}. {r.place}({r.count})"
                        for i, r in enumerate(top5.itertuples()))
        return top5["place"].tolist(), msg
    except Exception as e:
        print("people_high5 error:", e)
        if tk:
            safe_reply(tk, TextSendMessage(_t('data_fetch_failed')),uid)
        return [], _t('data_fetch_failed')


def send_questionnaire(tk,uid):
    btn = ButtonsTemplate(
        title=to_en("填寫問卷") if user_language == "en" else "填寫問卷",
        text=_t('reply_questionnaire'),
        actions=[URIAction(
            label=to_en("開始填寫") if user_language == "en" else "開始填寫",
            uri=GOOGLE_FORM_URL
        )]
    )
    safe_reply(tk, TemplateSendMessage(
        alt_text=_t('reply_questionnaire'),
        template=btn
    ),uid)

@measure_time
def send_crowd_analysis(tk,uid):
    safe_reply(tk, [
        TextSendMessage("https://how-many-people.eeddyytaddy.workers.dev")
    ],uid)


@measure_time
def recommend_general_places(tk, uid):
    """
    一般景點推薦：加入性別轉換後的模型呼叫
    """
    lang = _get_lang(uid)
    try:
        # 1) 人潮前五
        dont_go, _ = people_high5(tk,uid)

        # 2) 天氣、溫度、潮汐
        try:
            raw_weather = Now_weather.weather()
            w_str = raw_weather
        except:
            w_str = "晴"
        try:
            t = float(Now_weather.temperature())
        except:
            t = 25.0
        try:
            tide = float(Now_weather.tidal())
        except:
            tide = 0.0

        # 3) 性別 & 年齡轉換
        raw_gender = user_gender.get(uid, "")
        gender_code = FlexMessage.classify_gender(raw_gender)
        age = user_age.get(uid, 30)

        # 4) 模型推薦
        rec = XGBOOST_predicted.XGboost_recommend2(
            np.array([w_str]), gender_code, age, tide, t, dont_go
        )

        # 5) 產生 Flex Message
        website, img, maplink = PH_Attractions.Attractions_recommend(rec)

        msgs = [
            TextSendMessage(text=_t("system_recommend", lang)),
            TextSendMessage(text=rec),
            ImageSendMessage(original_content_url=f"{img}.jpg", preview_image_url=f"{img}.jpg"),
            TextSendMessage(text=website),
            TextSendMessage(text=maplink)
        ]
        safe_reply(tk, msgs,uid)
    except Exception as e:
        print("❌ recommend_general_places error:", e)
        safe_reply(tk, TextSendMessage(text=_t('data_fetch_failed', lang)),uid)


@measure_time
def recommend_sustainable_places(tk, uid):
    """
    永續觀光推薦（含性別／年齡轉換）
    1. 取得人潮 Top-5 → 避免推薦
    2. 讀天氣／溫度／潮汐並做標籤映射
    3. 依性別‧年齡跑 XGBoost 推薦
    4. 取景點資料，回傳「說明文字 ＋ 圖片」
    """
    lang = _get_lang(uid)

    try:
        # ---------- 1) 人潮 ----------
        dont_go, crowd_msg = people_high5(tk,uid)

        # ---------- 2) 天氣 ----------
        try:
            raw_weather = Now_weather.weather()
        except Exception:
            raw_weather = "晴"

        weather_map = {
            '晴':  '晴',  '多雲': '多雲', '陰': '陰',
            '小雨': '下雨', '中雨': '下雨', '大雨': '下雨', '雷陣雨': '下雨'
        }
        w_str = weather_map.get(raw_weather, '晴')

        # ---------- 3) 溫度‧潮汐 ----------
        try:
            temp_c = float(Now_weather.temperature() or 25.0)
        except Exception:
            temp_c = 25.0
        try:
            tide   = float(Now_weather.tidal() or 0.0)
        except Exception:
            tide   = 0.0

        # ---------- 4) 使用者資料 ----------
        raw_gender  = user_gender.get(uid, "")
        gender_code = FlexMessage.classify_gender(raw_gender)   # 0/1/2
        age         = user_age.get(uid, 30)

        # ---------- 5) XGBoost 推薦 ----------
        try:
            rec = ML.XGboost_recommend3(
                np.array([w_str]), gender_code, age, tide, temp_c, dont_go
            )
        except ValueError as e:          # 若出現 unseen label
            print("XGBoost fallback:", e)
            rec = ML.XGboost_recommend3(
                np.array(['晴']), gender_code, age, tide, temp_c, dont_go
            )

        # 如果結果還落在「不建議前往」名單，就再跑一次
        if rec in dont_go:
            rec = ML.XGboost_recommend3(
                np.array([w_str]), gender_code, age, tide, temp_c, dont_go
            )

        # ---------- 6) 取景點資訊 ----------
        web, img, maplink = PH_Attractions.Attractions_recommend1(rec)

        # Robust 圖片 URL
        if img.startswith(("http://", "https://")):
            img_url = img
        elif "imgur.com" in img:         # 轉 i.imgur.com 直連
            _id = img.rstrip("/").split("/")[-1]
            img_url = f"https://i.imgur.com/{_id}.jpg"
        else:
            img_url = f"https://{img.lstrip('/')}.jpg"

        # ---------- 7) 組訊息並送出 ----------
        header = f"📊 {crowd_msg}"
        title  = to_en('永續觀光') if lang == 'en' else '永續觀光'
        body   = f"{header}\n{title}：{rec}\n{web}\n{maplink}"

        safe_reply(tk, [
            TextSendMessage(text=body),
            ImageSendMessage(
                original_content_url=img_url,
                preview_image_url   =img_url
            )
        ],uid)

    except Exception as e:
        print("❌ recommend_sustainable_places error:", e)
        safe_reply(tk, TextSendMessage(text=_t('data_fetch_failed', lang)),uid)


@measure_time
def search_nearby_places(replyTK, uid, keyword):
    """
    根據關鍵字搜尋附近景點，並回傳多語 Carousel
    """
    lang = _get_lang(uid)

    # 1) 從記憶體讀取該使用者位置
    loc = user_location.get(uid)
    if not loc:
        safe_reply(replyTK, TextSendMessage(text=_t("cannot_get_location", lang)),uid)
        return
    lat, lon = loc

    # 2) 呼叫 Google Maps Nearby Search
    try:
        Googlemap_function.googlemap_search_nearby(lat, lon, keyword)
    except Exception as e:
        print("googlemap_search_nearby error:", e)
        safe_reply(replyTK, TextSendMessage(text=_t("data_fetch_failed", lang)),uid)
        return

    # 3) 產生並回傳 Carousel
    try:
        contents = FlexMessage.Carousel_contents(RECOMMEND_CSV, uid)
        carousel = FlexMessage.Carousel(contents, uid)
        safe_reply(replyTK, carousel,uid)
    except Exception as e:
        print("Carousel generation error:", e)
        safe_reply(replyTK, TextSendMessage(text=_t("data_fetch_failed", lang)),uid)

        
@measure_time
def send_rental_car(reply_token, uid):
    """
    根據使用者語系自動切換中／英文，
    回覆租車推薦連結。
    """
    # 1. 取出該 user 的語系
    lang = _get_lang(uid)

    # 2. 從 TEXTS 裡拿提示文字（在 zh2en.py 已定義）
    prompt = _t("visit_cars_url", lang)

    # 3. 固定的租車 URL
    url = "https://penghu-car-rental-agency.eeddyytaddy.workers.dev"

    # 4. 回覆兩則訊息：提示文字 + 連結
    safe_reply(reply_token, [
        TextSendMessage(text=prompt),
        TextSendMessage(text=url)
    ],uid)


@measure_time
def handle_ask_language(uid, replyTK):
    """第一步：請使用者選擇語言"""
    prompt = _t("ask_language", "zh")
    qr = QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="中文(Chinese)", text="中文")),
        QuickReplyButton(action=MessageAction(label="英文(English)", text="English"))
    ])
    safe_reply(replyTK, TextSendMessage(text=prompt, quick_reply=qr),uid)
    user_stage[uid] = 'got_language'

@measure_time
def handle_language(uid, text, replyTK):
    low = text.lower()
    if low in ("中文", "zh"):
        user_language[uid] = "zh"
    elif low in ("english", "en"):
        user_language[uid] = "en"
    else:
        safe_reply(replyTK, TextSendMessage(text=_t("invalid_language", _get_lang(uid))),uid)
        return

    user_stage[uid] = 'got_age'
    safe_reply(replyTK, TextSendMessage(text=_t("ask_age", _get_lang(uid))),uid)


@measure_time
def handle_gender_buttons(uid, lang, replyTK):
    """第三步（年齡後）：顯示性別選擇按鈕"""
    GENDER_LABEL = {"男": "Male", "女": "Female", "其他": "Other"}
    actions = [
        MessageAction(
            label=GENDER_LABEL[g] if lang=='en' else g,
            text=GENDER_LABEL[g] if lang=='en' else g
        )
        for g in ["男", "女", "其他"]
    ]
    tpl = ButtonsTemplate(text=_t("ask_gender", lang), actions=actions)
    safe_reply(replyTK, TemplateSendMessage(alt_text=_t("ask_gender", lang), template=tpl),uid)
    user_stage[uid] = 'got_gender'

@measure_time
def handle_gender(uid, text, replyTK):
    ENG2ZH = {"Male": "男", "Female": "女", "Other": "其他"}
    zh_text = ENG2ZH.get(text, text)
    if zh_text not in ("男", "女", "其他"):
        safe_reply(replyTK, TextSendMessage(text=_t("invalid_gender", _get_lang(uid))),uid)
        return

    user_gender[uid] = zh_text
    user_stage[uid]  = 'got_location'
    safe_reply(replyTK, FlexMessage.ask_location(),uid)


@measure_time
def handle_location(uid, msg, replyTK):
    """
    第五步：處理使用者傳來的位置訊息，
    並用記憶體字典(user_location)存起來，然後提示選擇天數
    """
    # 1) 從訊息取出地址與經緯度
    addr = msg["address"]
    lat  = msg["latitude"]
    lon  = msg["longitude"]

    # 2) 存到 shared.user_location (記憶體字典)，每個 user_id 獨立
    user_location[uid] = (lat, lon)

    # 3) 準備 QuickReply 讓使用者選擇行程天數
    lang = _get_lang(uid)
    days = ["兩天一夜", "三天兩夜", "四天三夜", "五天四夜"]
    qr_items = [
        QuickReplyButton(
            action=MessageAction(
                label=to_en(d) if lang == 'en' else d,
                text =to_en(d) if lang == 'en' else d
            )
        )
        for d in days
    ]

    # 4) 更新使用者階段並回覆
    user_stage[uid] = 'got_days'
    safe_reply(
        replyTK,
        TextSendMessage(
            text=_t("position_saved", lang),
            quick_reply=QuickReply(items=qr_items)
        ),uid
    )


@measure_time
def handle_days(uid, text, replyTK):
    zh_days = ["兩天一夜", "三天兩夜", "四天三夜", "五天四夜"]
    eng2zh  = {to_en(d): d for d in zh_days}
    lang    = _get_lang(uid)
    choice  = eng2zh.get(text, text)

    if choice not in zh_days:
        safe_reply(replyTK, TextSendMessage(text=_t("invalid_days", lang)),uid)
        return

    user_trip_days[uid]   = choice
    user_preparing[uid]   = True
    user_plan_ready[uid]  = False
    user_stage[uid]       = 'ready'

    threading.Thread(
        target=_background_planning,
        args=(choice, replyTK, uid),
        daemon=True
    ).start()

    safe_reply(replyTK, TextSendMessage(text=_t("please_wait", lang)),uid)


@measure_time
def handle_free_command(uid, text, replyTK):
    """
    Ready 階段的自由指令處理：包含「收集資料」「景點人潮」「行程規劃」
    「景點推薦」「永續觀光」「附近搜尋」「關鍵字搜尋」「租車」等指令。
    """
    from linebot.models import (
        TextSendMessage, TemplateSendMessage, ConfirmTemplate,
        QuickReply, QuickReplyButton, MessageAction, StickerSendMessage
    )

    low = text.lower()
    lang = _get_lang(uid)

    # 使用者目前狀態
    preparing = user_preparing.get(uid, False)
    plan_ready = user_plan_ready.get(uid, False)
    days = user_trip_days.get(uid)
    # 天數標籤：中/英文
    days_label = to_en(days) if lang == 'en' else days

    # 指令集合
    recollect_keys = {
        "收集資料&修改資料", "收集資料&修改資料(data collection)",
        "data collection", "collect data", "1"
    }
    crowd_keys = {
        "景點人潮", "景點人潮(crowd analyzer)",
        "crowd analyzer", "crowd analysis", "crowd info", "3"
    }
    plan_keys = {
        "行程規劃", "行程規劃(itinerary planning)",
        "itinerary planning", "plan itinerary", "6"
    }
    recommend_keys = {
        "景點推薦", "景點推薦(attraction recommendation)",
        "attraction recommendation", "recommend spot", "2"
    }
    sustainable_keys = {
        "永續觀光", "永續觀光(sustainable tourism)",
        "sustainable tourism", "2-1"
    }
    general_keys = {
        "一般景點推薦", "一般景點推薦(general recommendation)",
        "general recommendation", "2-2"
    }
    nearby_keys = {
        "附近搜尋", "附近搜尋(nearby search)",
        "nearby search", "4"
    }
    rental_keys = {
        "租車", "租車(car rental information)",
        "car rental information", "car rental", "5"
    }
    keyword_map = {
        "餐廳": "restaurants",
        "停車場": "parking",
        "風景區": "scenic spots",
        "住宿": "accommodation"
    }

    # 1) 收集資料
    if low in recollect_keys:
        prompt = _t("ask_language", "zh")
        qr = QuickReply(items=[
            QuickReplyButton(action=MessageAction(label="中文(Chinese)", text="中文")),
            QuickReplyButton(action=MessageAction(label="英文(English)", text="English"))
        ])
        safe_reply(replyTK, TextSendMessage(text=prompt, quick_reply=qr),uid)
        user_stage[uid] = 'got_language'
        return

    # 2) 景點人潮
    if low in crowd_keys:
        send_crowd_analysis(replyTK,uid)
        return

    # 3) 行程規劃
    if low in plan_keys:
        if preparing:
            safe_reply(replyTK, TextSendMessage(text=_t("prep_in_progress", lang)),uid)
        elif plan_ready:
            # 系統說明文字
            if lang == 'en':
                desc1 = f"Using machine learning based on relevance, we found the best {days_label} itinerary for you"
            else:
                desc1 = f"以機器學習依據相關性，找尋過往數據最適合您的{days_label}行程"
            
            sys_label = _t("system_route", lang)
            if lang == 'en':
                desc_sys = (
                    f"【{sys_label}】\n"
                    "1. Show full route (red line).\n"
                    "2. Show segment by segment (blue line).\n"
                    "3. Clear system route."
                )
            else:
                desc_sys = (
                    f"【{sys_label}】依照人潮較少規劃\n"
                    "1. 整段顯示完整路線（紅線）。\n"
                    "2. 分段逐段顯示（藍線）。\n"
                    "3. 清除系統路線。"
                )

            usr_label = _t("user_route", lang)
            if lang == 'en':
                desc_usr = (
                    f"【{usr_label}】\n"
                    "1. Tap \"Add to route\" to include in list.\n"
                    "2. Show all at once (green line).\n"
                    "3. Show segment by segment (orange line).\n"
                    "4. Clear user route."
                )
            else:
                desc_usr = (
                    f"【{usr_label}】\n"
                    "1. 點「加入路線」加入清單。\n"
                    "2. 一次性顯示（綠線）。\n"
                    "3. 分段逐段顯示（橘線）。\n"
                    "4. 清除使用者路線。"
                )
            safe_reply(replyTK, FlexMessage.ask_route_option(),uid)
            safe_push(uid, [
                TextSendMessage(text=desc1),
                TextSendMessage(text=desc_sys),
                TextSendMessage(text=desc_usr),
            ])
        else:
            safe_reply(replyTK, TextSendMessage(text=_t("collect_info", lang)),uid)
        return

    # 4) 景點推薦 (詢問是否永續)
    if low in recommend_keys:
        yes_lbl = _t("yes", lang)
        no_lbl = _t("no", lang)
        payload_yes = "永續觀光" if lang=='zh' else "sustainable tourism"
        payload_no = "一般景點推薦" if lang=='zh' else "general recommendation"
        tpl = ConfirmTemplate(
            text=_t("ask_sustainable", lang),
            actions=[
                MessageAction(label=yes_lbl, text=payload_yes),
                MessageAction(label=no_lbl, text=payload_no)
            ]
        )
        safe_reply(replyTK, TemplateSendMessage(alt_text=_t("ask_sustainable", lang), template=tpl),uid)
        return

    # 5) 永續或一般推薦
    if low in sustainable_keys:
        recommend_sustainable_places(replyTK, uid)
        return
    if low in general_keys:
        recommend_general_places(replyTK, uid)
        return

    # 6) 附近搜尋
    if low in nearby_keys:
        safe_reply(replyTK, FlexMessage.ask_keyword(),uid)
        return

    # 7) 關鍵字搜尋
    if text in keyword_map or low in set(keyword_map.values()):
        if low in set(keyword_map.values()):
            zh = next(k for k,v in keyword_map.items() if v==low)
            search_nearby_places(replyTK, uid, zh)
        else:
            search_nearby_places(replyTK, uid, text)
        return

    # 8) 租車
    if low in rental_keys:
        send_rental_car(replyTK, uid)
        return

    # 9) 其他忽略
    return



# ========== LINE 主路由 ========== #
@app.route("/", methods=["POST"])
def linebot_route():
    body = request.get_json(silent=True) or {}
    events = body.get("events", [])
    
    if not events:
        return "OK"

    # 處理每個事件
    for ev in events:  # 改為迴圈處理所有事件
        try:
            handle_single_event(ev)
        except Exception as e:
            print(f"Error handling event: {e}")
    
    return "OK"

def handle_single_event(ev):
    """處理單一事件"""
    ev_type = ev.get("type")
    uid = ev["source"]["userId"]
    lang = _get_lang(uid)
    stage = user_stage.get(uid, 'ask_language')  # 預設階段
    replyTK = ev.get("replyToken")
    
    # 檢查 reply token 是否有效
    if not replyTK:
        print("Warning: No reply token in event")
        return
    
    print(f"Handling event type: {ev_type}, user: {uid}, stage: {stage}")

    # 1) PostbackEvent：處理按鈕
    if ev_type == "postback":
        handle_postback_event(ev, uid, lang, stage, replyTK)
        return

    # 2) MessageEvent：階段式對話 + 自由指令
    elif ev_type == "message":
        handle_message_event(ev, uid, lang, stage, replyTK)
        return

    # 3) 其他事件類型
    else:
        print(f"Unhandled event type: {ev_type}")
        return

def handle_postback_event(ev, uid, lang, stage, replyTK):
    """處理 Postback 事件"""
    data = ev["postback"]["data"]
    print(f"Postback data: {data}")

    # 性別按鈕
    if data in ("男", "女", "其他"):
        handle_gender(uid, data, replyTK)
        return

    # 天數按鈕
    if data in ("兩天一夜", "三天兩夜", "四天三夜", "五天四夜"):
        user_trip_days[uid] = data
        user_preparing[uid] = True
        user_plan_ready[uid] = False
        user_stage[uid] = 'ready'
        
        # 先回覆等待訊息
        safe_reply(replyTK, TextSendMessage(text=_t("please_wait", lang)),uid)
        
        # 然後啟動背景處理
        threading.Thread(
            target=_background_planning,
            args=(data, None, uid),  # 不傳 reply_token 給背景處理
            daemon=True
        ).start()
        return

    # 系統路線 / 使用者路線
    sys_zh, usr_zh = "系統路線", "使用者路線"
    sys_en, usr_en = to_en(sys_zh), to_en(usr_zh)
    
    if data in (sys_zh, sys_en):
        try:
            lat, lon = get_location.get_location(LOCATION_FILE)
            uid_qs = urllib.parse.quote_plus(uid)
            url = f"https://system-plan.eeddyytaddy.workers.dev/?uid={uid_qs}&lat={lat}&lng={lon}"
            safe_reply(replyTK, TextSendMessage(text=url),uid)
            user_stage[uid] = 'ready'
        except Exception as e:
            print(f"Error getting location: {e}")
            safe_reply(replyTK, TextSendMessage(text=_t("cannot_get_location", lang)),uid)
        return
        
    if data in (usr_zh, usr_en):
        try:
            lat, lon = get_location.get_location(LOCATION_FILE)
            uid_qs = urllib.parse.quote_plus(uid)
            url = f"https://user-plan.eeddyytaddy.workers.dev/?uid={uid_qs}&lat={lat}&lng={lon}"
            safe_reply(replyTK, TextSendMessage(text=url),uid)
            user_stage[uid] = 'ready'
        except Exception as e:
            print(f"Error getting location: {e}")
            safe_reply(replyTK, TextSendMessage(text=_t("cannot_get_location", lang)),uid)
        return

def handle_message_event(ev, uid, lang, stage, replyTK):
    """處理訊息事件"""
    msg = ev["message"]
    msgType = msg.get("type")
    text = (msg.get("text") or "").strip()
    
    print(f"Message type: {msgType}, text: {text}, stage: {stage}")

    # 根據階段處理訊息
    if stage == 'ask_language' and msgType == "text":
        handle_ask_language(uid, replyTK)
        return

    if stage == 'got_language' and msgType == "text":
        handle_language(uid, text, replyTK)
        return

    if stage == 'got_age' and msgType == "text":
        try:
            age = int(text)
            if 0 <= age <= 120:
                user_age[uid] = age
                handle_gender_buttons(uid, lang, replyTK)
            else:
                safe_reply(replyTK, TextSendMessage(text=_t("enter_valid_age", lang)),uid)
        except ValueError:
            safe_reply(replyTK, TextSendMessage(text=_t("enter_number", lang)),uid)
        return

    if stage == 'got_gender' and msgType == "text":
        handle_gender(uid, text, replyTK)
        return

    if stage == 'got_location' and msgType == "location":
        handle_location(uid, msg, replyTK)
        return

    if stage == 'got_days' and msgType == "text":
        handle_days(uid, text, replyTK)
        return

    if stage == 'ready' and msgType == "text":
        handle_free_command(uid, text, replyTK)
        return

    # 處理其他訊息類型
    if msgType == "image":
        safe_reply(replyTK, TextSendMessage(text=_t("data_fetch_failed", lang)),uid)
        return
        
    if msgType == "sticker":
        safe_reply(replyTK, StickerSendMessage(
            package_id=msg["packageId"], 
            sticker_id=msg["stickerId"]
        ),uid)
        return

# ========== Postback ========== #
@handler.add(PostbackEvent)
def handle_postback(event):
    uid  = event.source.user_id
    data = event.postback.data
    tk   = event.reply_token
    lang = _get_lang(uid)

    # 1) 性別按鈕
    if data in ("男", "女", "其他"):
        gender_1 = FlexMessage.classify_gender(data)
        user_stage[uid] = 'got_location'
        safe_reply(tk, FlexMessage.ask_location(),uid)
        return

    # 2) 天數按鈕
    if data in ("兩天一夜", "三天兩夜", "四天三夜", "五天四夜"):
        global preparing, plan_ready
        preparing  = True
        plan_ready = False
        user_stage[uid] = 'ready'
        threading.Thread(
            target=_background_planning,
            args=(data, tk, uid),
            daemon=True
        ).start()
        safe_reply(tk, TextSendMessage(text=_t("please_wait", lang)),uid)
        return

    # 3) 系統路線 / 使用者路線 按鈕
    sys_zh, usr_zh = "系統路線", "使用者路線"
    sys_en, usr_en = to_en(sys_zh), to_en(usr_zh)
    valid_sys = {sys_zh, sys_en}
    valid_usr = {usr_zh, usr_en}

    if data in valid_sys:
        try:
            lat, lon = get_location.get_location(LOCATION_FILE)
            url = f"https://system-plan.eeddyytaddy.workers.dev?lat={lat}&lng={lon}"
            safe_reply(tk, TextSendMessage(text=url),uid)
        except:
            safe_reply(tk, TextSendMessage(text=_t("cannot_get_location", lang)),uid)
        user_stage[uid] = 'ready'
        return

    if data in valid_usr:
        try:
            lat, lon = get_location.get_location(LOCATION_FILE)
            url = f"https://user-plan.eeddyytaddy.workers.dev?lat={lat}&lng={lon}"
            safe_reply(tk, TextSendMessage(text=url),uid)
        except:
            safe_reply(tk, TextSendMessage(text=_t("cannot_get_location", lang)),uid)
        user_stage[uid] = 'ready'
        return

    # 其餘 Postback 直接忽略
    print("Unhandled postback:", data)
import threading
import time

def cleanup_used_tokens():
    """定期清理已使用的 reply token (每小時執行一次)"""
    while True:
        time.sleep(3600)  # 1小時
        used_reply_tokens.clear()
        print("Cleaned up used reply tokens")

# 啟動清理執行緒
cleanup_thread = threading.Thread(target=cleanup_used_tokens, daemon=True)
cleanup_thread.start()

# ================= MAIN =========================================== #
if __name__ == "__main__":
    print("🚀 Flask server start …")
    os.environ.setdefault('APP_ENV', 'loadtest')
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",8000)), debug=True)

# ---------------- END OF app.py ------------------------------------
