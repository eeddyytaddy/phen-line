# app.py 
from gevent import monkey
monkey.patch_all()
from gevent.pool import Pool
from linebot.models import TextSendMessage
import os
import io
import json
import csv
import sqlite3
import threading
threading._after_fork = lambda *args, **kwargs: None
threading.Thread._stop   = lambda self: None
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

# Matplotlib 無頭模式
import matplotlib
import urllib.parse

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
import shared
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
MAX_PARALLEL_PLANNING = int(os.getenv("MAX_PARALLEL_PLANNING", "40"))
PLANNING_POOL = Pool(MAX_PARALLEL_PLANNING)
# 常數
#PHP_ngrok = "https://flask-service2.peterlinebot.ip-ddns.com"
PHP_NGROK       = "https://penghu-linebot.onrender.com"
GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSeT7kHB3bsE7rmxqJdzG42XfSS9ewNBBZPVH3xxunpYVcyDag/viewform?usp=header"
GOOGLE_API_KEY  = os.getenv("GOOGLE_MAPS_API_KEY")
# ─────────────── 每-user 語系設定 & 其他全域狀態 ───────────────



approveLangRespond  = False
approveAgeRespond   = False
approveGender       = False
approveDaysRespond  = False
# ─────────────── 多語小助手 ───────────────
def enqueue_planning(option: str, reply_token: str | None, user_id: str) -> None:
    """
    把 _background_planning 排進固定大小的 Greenlet 池。
    若池子滿了，立刻回覆「系統忙碌，請稍候」。
    """
    if PLANNING_POOL.free_count() == 0:
        lang = _get_lang(user_id)
        safe_reply(
            reply_token,
            TextSendMessage(text=_t("system_busy", lang)),
            user_id,
        )
        return

    PLANNING_POOL.spawn(_background_planning, option, reply_token, user_id)

def _t(key: str, lang: str) -> str:
    """
    從 I18N 裡撈對應語系字串；若找不到，回傳 key 本身。
    lang: 'zh' or 'en'
    """
    return I18N.get(lang, I18N['zh']).get(key, key)

def _get_lang(uid: str) -> str:
    """取得該 user 的語系設定"""
    return shared.user_language.get(uid, 'zh')

# ─────────────── LINE 安全封裝 ───────────────
used_reply_tokens = set()

def safe_reply(token, msgs, uid=None):
    """
    安全的 reply 函式，避免重複使用 replyToken。
    測試模式下可跳過實際 LINE 回覆呼叫，防止無效 token 錯誤。
    """
    if not token:
        print("Warning: reply token is None or empty")
        return

    # 避免同一個 token 重複用
    if token in used_reply_tokens:
        print(f"Warning: Reply token {token} already used, skipping reply")
        return

    # **新增：測試環境跳過 LINE API 呼叫**
    test_mode = os.getenv("TEST_MODE", "0") == "1"
    # 簡單判斷：token 含有 '-' 視為非 LINE 平台生成（Locust UUID）
    if test_mode or "-" in token:
        print(f"[TestMode] Skip reply_message for token: {token}")
        used_reply_tokens.add(token)
        # 測試模式下直接視為成功回覆，不呼叫 LINE 平台
        return

    # 確保 msgs 為 list
    if not isinstance(msgs, list):
        msgs = [msgs]

    try:
        # 嘗試呼叫 LINE 回覆 API
        line_bot_api.reply_message(token, msgs)
        used_reply_tokens.add(token)
        print(f"✅ Reply sent successfully with token: {token}")
    except LineBotApiError as e:
        # 取得錯誤細節
        status_code = getattr(e, "status_code", None)
        request_id  = getattr(e, "request_id", None)
        error_message = e.error.message if hasattr(e, "error") and e.error else str(e)
        print(f"❌ safe_reply error: status_code={status_code}, request_id={request_id}, message={error_message}")
        # 標記 token 已使用，避免重複
        used_reply_tokens.add(token)
        # 若有提供 uid，改用 push 補發訊息
        if uid:
            print(f"↪️ safe_reply fallback to push for user {uid}")
            try:
                safe_push(uid, msgs)
            except Exception as e2:
                print(f"   ⚠️ safe_push fallback failed: {e2}")
    except Exception as e:
        # 其它非 LineBotApiError 的例外
        print(f"safe_reply unexpected error: {e}")



from linebot.exceptions import LineBotApiError
from linebot.models.send_messages import SendMessage
import json

def safe_push(uid, msgs):
    """
    安全的 push 函式：
    1) 只對看起來合法的 LINE userId (U 開頭) 嘗試 get_profile。
    2) get_profile 若 404 (user not following)，直接跳過。
    3) 其它錯誤、或 uid 無效，則記錄後 skip。
    """
    # 只 push 給 LINE userId
    if not uid or not isinstance(uid, str) or not uid.startswith("U"):
        print(f"Warning: skip safe_push due to invalid userId: {uid}")
        return

    if not isinstance(msgs, list):
        msgs = [msgs]

    # 驗證用戶是否為好友
    try:
        profile = line_bot_api.get_profile(uid)
        print(f"User profile ok: {profile.display_name} ({uid})")
    except LineBotApiError as e:
        status = e.status_code
        msg    = e.error.message if e.error else str(e)
        if status == 404:
            print(f"safe_push aborted: user {uid} not following (404)")
            return
        else:
            print(f"safe_push get_profile error: status_code={status}, message={msg}")
            return
    except Exception as e:
        print(f"safe_push unexpected error on get_profile: {e}")
        return

    # 分 batch 推送
    batches = [msgs[i:i+5] for i in range(0, len(msgs), 5)]
    for idx, batch in enumerate(batches, 1):
        payloads = []
        for m in batch:
            if hasattr(m, "as_json_dict"):
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
        shared.user_plan_ready[user_id] = True
        
        # 規劃完成後推送通知
        lang = _get_lang(user_id)
        safe_push(user_id, TextSendMessage(text=_t("planning_completed", lang)))
        
    except Exception as e:
        print(f"Background planning failed: {e}")
        lang = _get_lang(user_id)
        safe_push(user_id, TextSendMessage(text=_t("planning_failed", lang)))
    finally:
        shared.user_preparing[user_id] = False
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
    loc = shared.user_location.get(user_id)
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

def run_ml_sort(option, reply_token, user_id, df_plan):
    """
    以 XGBoost 依性別、年齡做排序，回傳 userID list
    """
    # 1) 取出原始文字性別，並轉成數值
    raw_gender = shared.user_gender.get(user_id, "")
    gender = FlexMessage.classify_gender(raw_gender)  # 0=男, 1=女, 2=其他

    # 2) 取年齡
    age = shared.user_age.get(user_id, 30)

    # 3) 印出 debug 訊息並呼叫 XGBoost
    #print(f"run_ml_sort: gender={gender}, age={age}, df_plan.dtypes={df_plan.dtypes}")
    return ML.XGboost_plan(df_plan, gender, age)



# ---- 2) 景點過濾 (Attraction Filtering) ----

def run_filter(option, reply_token, user_id, csv_path, userID):
    """
    根據需求過濾景點（例如距離、人潮…）
    """
    Filter.filter(csv_path, userID)


# ---- 3) 景點重排名 (Attraction Ranking) ----

def run_ranking(option, reply_token, user_id, plan_csv):
    """
    根據即時人潮和距離再對行程排序，並寫回 CSV
    """
    update_plan_csv_with_populartimes(plan_csv, user_id, crowd_source="realtime")


# ---- 4) 上傳資料 (Data to Database) ----

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
    if shared.user_gender.get(user_id) is None or shared.user_age.get(user_id) is None:
        lang = _get_lang(user_id)
        safe_reply(
            reply_token,
            TextSendMessage(text=_t('collect_info', lang)),
            user_id
        )
        shared.user_preparing[user_id] = False
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
        shared.user_preparing[user_id] = False
        return

    # 2. 機器學習排序
    try:
        sorted_user_list = run_ml_sort(option, reply_token, user_id, df_plan)
    except Exception as e:
        print("XGboost_plan error:", e)
        lang = _get_lang(user_id)
        safe_push(user_id, TextSendMessage(text=_t('data_fetch_failed', lang)))
        shared.user_preparing[user_id] = False
        return

    # 3. 景點過濾
    try:
        run_filter(option, reply_token, user_id, csv_path, sorted_user_list)
    except Exception as e:
        print("filter error:", e)
        lang = _get_lang(user_id)
        safe_push(user_id, TextSendMessage(text=_t('data_fetch_failed', lang)))
        shared.user_preparing[user_id] = False
        return

    # 4. 重排名（加入即時人潮與距離）
    try:
        run_ranking(option, reply_token, user_id, PLAN_CSV)
    except Exception as e:
        print("ranking error:", e)
        lang = _get_lang(user_id)
        safe_push(user_id, TextSendMessage(text=_t('data_fetch_failed', lang)))
        shared.user_preparing[user_id] = False
        return

    # 5. 上傳最終結果
    try:
        run_upload(option, reply_token, user_id)
    except Exception as e:
        print("upload error:", e)
        lang = _get_lang(user_id)
        safe_push(user_id, TextSendMessage(text=_t('data_fetch_failed', lang)))
        shared.user_preparing[user_id] = False
        return

    # 6. 標記該使用者的規劃已完成
    shared.user_plan_ready[user_id] = True
    shared.user_preparing[user_id]  = False

    # 可選）如需立即推送結果給使用者，取消下行註解：
    # safe_push(user_id, FlexMessage.show_plan(PLAN_CSV))




def people_high5(tk, uid):
    """回傳目前時段最壅擠前 5 名 (list, text)"""
    try:
        df = pd.read_csv("daily_crowd_stats.csv", encoding="utf-8-sig")
        hr = dt.now().hour
        top5 = (
            df[df["hour"] == hr]
              .sort_values("count", ascending=False)
              .head(5)
        )
        msg = "\n".join(
            f"{i+1}. {r.place}({r.count})"
            for i, r in enumerate(top5.itertuples())
        )
        return top5["place"].tolist(), msg
    except Exception as e:
        print("people_high5 error:", e)
        # 取得使用者語系
        lang = _get_lang(uid)
        if tk:
            safe_reply(
                tk,
                TextSendMessage(text=_t('data_fetch_failed', lang)),
                uid
            )
        return [], _t('data_fetch_failed', lang)

def send_questionnaire(tk,uid):
    lang = _get_lang(uid)
    btn = ButtonsTemplate(
        title=to_en("填寫問卷") if lang == "en" else "填寫問卷",
        text=_t('reply_questionnaire'),
        actions=[URIAction(
            label=to_en("開始填寫") if shared.user_language == "en" else "開始填寫",
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
        raw_gender = shared.user_gender.get(uid, "")
        gender_code = FlexMessage.classify_gender(raw_gender)
        age = shared.user_age.get(uid, 30)

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
    1. 避開擁擠 Top-5
    2. 取天氣／溫度／潮汐（safe_call＋safe_float）
    3. 以 XGBoost 做推薦（safe_call）
    4. 拉景點資料、組訊息並回傳
    """
    # ---------- 共用工具 --------------------------------------------------
    import time, numpy as np
    from requests.exceptions import ConnectionError, Timeout, RequestException
    from http.client import RemoteDisconnected

    def safe_float(v, default=0.0):
        try:
            return float(v)
        except (ValueError, TypeError):
            print(f"⚠️ safe_float: 轉換失敗 → {default}  (input={v})")
            return default

    def safe_call(fn, default, *args, **kwargs):
        """
        對任何可能連網的函式提供 3 次重試。
        捕捉範圍：ConnectionError / Timeout / RemoteDisconnected / RequestException
        """
        for i in range(3):
            try:
                return fn(*args, **kwargs)
            except (ConnectionError, Timeout, RemoteDisconnected, RequestException) as e:
                print(f"⚠️ safe_call {fn.__name__} 失敗 {i+1}/3：{e}")
                time.sleep(0.6 * (i + 1))
            except Exception as e:
                print(f"⚠️ safe_call {fn.__name__} 其它例外：{e}")
                break
        return default

    lang = _get_lang(uid)

    try:
        # ---------- 1) 人潮黑名單 ----------------------------------------
        dont_go, crowd_msg = people_high5(tk, uid)

        # ---------- 2) 天氣相關 ------------------------------------------
        raw_weather = safe_call(Now_weather.weather, "晴")
        w_str = {
            '晴': '晴', '多雲': '多雲', '陰': '陰',
            '小雨': '下雨', '中雨': '下雨', '大雨': '下雨', '雷陣雨': '下雨'
        }.get(raw_weather, '晴')

        temp_c = safe_float(safe_call(Now_weather.temperature, 25.0), 25.0)
        tide   = safe_float(safe_call(Now_weather.tidal,        0.0),  0.0)

        # ---------- 3) User profile -------------------------------------
        raw_gender  = shared.user_gender.get(uid, "")
        gender_code = FlexMessage.classify_gender(raw_gender)   # 0/1/2
        age         = shared.user_age.get(uid, 30)

        # ---------- 4) XGBoost 推薦 -------------------------------------
        def _run_xgb(weather_tag):
            return ML.XGboost_recommend3(
                np.array([weather_tag]), gender_code, age, tide, temp_c, dont_go
            )

        rec = safe_call(lambda: _run_xgb(w_str), "")
        if not rec:                         # 三次都失敗 → fallback
            rec = safe_call(lambda: _run_xgb('晴'), "山水沙灘")  # 固定備用景點

        # 如仍落在黑名單，再換一次
        if rec in dont_go:
            rec = safe_call(lambda: _run_xgb(w_str), rec)

        # ---------- 5) 景點資訊 -----------------------------------------
        web, img, maplink = safe_call(
            PH_Attractions.Attractions_recommend1,
            ("", "", ""),
            rec
        )

        # 圖片 URL 處理
        if img.startswith(("http://", "https://")):
            img_url = img
        elif "imgur.com" in img:
            img_url = f"https://i.imgur.com/{img.rstrip('/').split('/')[-1]}.jpg"
        else:
            img_url = f"https://{img.lstrip('/')}.jpg" if img else ""

        # ---------- 6) 成品訊息 -----------------------------------------
        header = f"📊 {crowd_msg}"
        title  = to_en('永續觀光') if lang == 'en' else '永續觀光'
        body   = f"{header}\n{title}：{rec}\n{web}\n{maplink}"

        msgs = [TextSendMessage(text=body)]
        if img_url:
            msgs.append(ImageSendMessage(
                original_content_url=img_url,
                preview_image_url   =img_url
            ))

        safe_reply(tk, msgs, uid)

    except Exception as e:
        print("❌ recommend_sustainable_places error:", e)
        safe_reply(tk, TextSendMessage(text=_t('data_fetch_failed', lang)), uid)



@measure_time
def search_nearby_places(replyTK, uid, keyword):
    """
    根據關鍵字搜尋附近景點，並回傳多語 Carousel
    """
    lang = _get_lang(uid)

    # 1) 從記憶體讀取該使用者位置
    loc = shared.user_location.get(uid)
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



def handle_ask_language(uid, replyTK):
    """第一步：請使用者選擇語言"""
    prompt = _t("ask_language", "zh")
    qr = QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="中文(Chinese)", text="中文")),
        QuickReplyButton(action=MessageAction(label="英文(English)", text="English"))
    ])
    safe_reply(replyTK, TextSendMessage(text=prompt, quick_reply=qr), uid)
    # 原來是 got_language，改成 ask_language
    shared.user_stage[uid] = 'ask_language'

@measure_time
def handle_language(uid, text, replyTK):
    low = text.lower()
    if low in ("中文", "zh"):
        shared.user_language[uid] = "zh"
    elif low in ("english", "en"):
        shared.user_language[uid] = "en"
    else:
        safe_reply(replyTK, TextSendMessage(text=_t("invalid_language", _get_lang(uid))),uid)
        return

    shared.user_stage[uid] = 'got_age'
    safe_reply(replyTK, TextSendMessage(text=_t("ask_age", _get_lang(uid))),uid)

# 在 app.py 中新增，放在 handle_language、handle_gender_buttons 之後，handle_message_event 之前
@measure_time
def handle_age(uid, text, replyTK):
    """
    處理使用者輸入的年齡 (stage='got_age')：
    1) 驗證整數範圍 0–120
    2) 存到 shared.user_age
    3) 呼叫 handle_gender_buttons 進入下一步
    4) 錯誤時回覆對應錯誤訊息
    """
    from linebot.models import TextSendMessage

    lang = _get_lang(uid)
    try:
        age = int(text)
        if 0 <= age <= 120:
            shared.user_age[uid] = age
            # 進入「選擇性別」階段
            handle_gender_buttons(uid, lang, replyTK)
        else:
            safe_reply(
                replyTK,
                TextSendMessage(text=_t("enter_valid_age", lang)),
                uid
            )
    except ValueError:
        safe_reply(
            replyTK,
            TextSendMessage(text=_t("enter_number", lang)),
            uid
        )


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
    shared.user_stage[uid] = 'got_gender'

@measure_time
def handle_gender(uid, text, replyTK):
    ENG2ZH = {"Male": "男", "Female": "女", "Other": "其他"}
    zh_text = ENG2ZH.get(text, text)
    if zh_text not in ("男", "女", "其他"):
        safe_reply(replyTK, TextSendMessage(text=_t("invalid_gender", _get_lang(uid))),uid)
        return

    shared.user_gender[uid] = zh_text
    shared.user_stage[uid]  = 'got_location'
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
    shared.user_location[uid] = (lat, lon)

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
    shared.user_stage[uid] = 'got_days'
    safe_reply(
        replyTK,
        TextSendMessage(
            text=_t("position_saved", lang),
            quick_reply=QuickReply(items=qr_items)
        ),uid
    )


# ──────────────────────────────────────────────────────────────────────────
# 處理使用者輸入「兩天一夜／三天兩夜／四天三夜／五天四夜」的文字訊息
# ──────────────────────────────────────────────────────────────────────────
@measure_time
def handle_days(user_id: str, text: str, reply_token: str) -> None:
    """
    依照使用者輸入（天數選項）更新狀態，並將行程規劃排入背景佇列。

    Parameters
    ----------
    user_id : str
        LINE 使用者 ID
    text : str
        使用者輸入的文字（可能是中文或經 to_en 處理過的英文）
    reply_token : str
        LINE reply token，用於立即回覆訊息
    """
    # 1) 支援的天數選項（中文）
    zh_days = ["兩天一夜", "三天兩夜", "四天三夜", "五天四夜"]
    # 2) 建立「英文→中文」對照，以防使用者傳的是英文代碼
    eng2zh = {to_en(d): d for d in zh_days}

    lang   = _get_lang(user_id)
    choice = eng2zh.get(text, text)          # 先嘗試轉回中文

    # ── 輸入不合法 ──
    if choice not in zh_days:
        safe_reply(
            reply_token,
            TextSendMessage(text=_t("invalid_days", lang)),
            user_id,
        )
        return

    # ── 更新共享狀態 ──
    shared.user_trip_days[user_id]  = choice
    shared.user_preparing[user_id]  = True
    shared.user_plan_ready[user_id] = False
    shared.user_stage[user_id]      = "ready"

    # ── 回覆「請稍候」，並將規劃任務排進固定大小的 Greenlet Pool ──
    safe_reply(
        reply_token,
        TextSendMessage(text=_t("please_wait", lang)),
        user_id,
    )
    enqueue_planning(choice, reply_token, user_id)



# app.py
# ----------------------------------------------------------------------
@measure_time
def handle_free_command(uid: str, text: str, replyTK) -> None:
    """
    Ready 階段的自由指令處理：
    包含「收集資料」「景點人潮」「行程規劃」「景點推薦」
         「永續觀光」「附近搜尋」「關鍵字搜尋」「租車」等指令。
    """

    # ---- 0. 前置 ------------------------------------------------------
    from linebot.models import (
        TextSendMessage, TemplateSendMessage, ConfirmTemplate,
        QuickReply, QuickReplyButton, MessageAction, StickerSendMessage
    )
    low  = text.lower()
    lang = _get_lang(uid)

    # 使用者狀態
    preparing   = shared.user_preparing.get(uid, False)
    plan_ready  = shared.user_plan_ready.get(uid, False)
    days        = shared.user_trip_days.get(uid)       # 例如 "三天兩夜"
    days_label  = to_en(days) if lang == "en" else days

    # ---- 1. 指令集合 --------------------------------------------------
    recollect_keys   = {"收集資料", "data collection", "collect data", "1"}
    crowd_keys       = {"景點人潮", "景點人潮(crowd analyzer)", "crowd analyzer",
                        "crowd analysis", "crowd info", "3"}
    plan_keys        = {"行程規劃", "行程規劃(itinerary planning)",
                        "itinerary planning", "plan itinerary", "6"}
    recommend_keys   = {"景點推薦", "景點推薦(attraction recommendation)",
                        "attraction recommendation", "recommend spot", "2"}
    sustainable_keys = {"永續觀光", "永續觀光(sustainable tourism)",
                        "sustainable tourism", "2-1"}
    general_keys     = {"一般景點推薦", "一般景點推薦(general recommendation)",
                        "general recommendation", "2-2"}
    nearby_keys      = {"附近搜尋", "附近搜尋(nearby search)", "nearby search", "4"}
    rental_keys      = {"租車", "租車(car rental information)",
                        "car rental information", "car rental", "5"}

    keyword_map = {"餐廳": "restaurants", "停車場": "parking",
                   "風景區": "scenic spots", "住宿": "accommodation"}
    is_keyword  = text in keyword_map or low in set(keyword_map.values())

    # ---- 2. 各指令邏輯 ------------------------------------------------

    # 2-1 收集 / 重啟流程
    if low in recollect_keys:
        handle_ask_language(uid, replyTK)
        return

    # 2-2 景點人潮
    if low in crowd_keys:
        send_crowd_analysis(replyTK, uid)
        return

    # 2-3 行程規劃 ------------------------------------------------------
    if low in plan_keys:
        # (a) 規劃中
        if preparing:
            safe_reply(replyTK, TextSendMessage(text=_t("still_processing", lang)), uid)
            return
        # (b) 規劃已完成
        if plan_ready:
            safe_reply(replyTK,
                       TextSendMessage(text=_t("plan_ready", lang).format(days_label)), uid)
            send_questionnaire(replyTK, uid)
            return
        # (c) 尚未開始 → 送進佇列
        if not days:
            # 尚未選天數
            safe_reply(replyTK, TextSendMessage(text=_t("ask_days", lang)), uid)
            return

        shared.user_preparing[uid]  = True
        shared.user_plan_ready[uid] = False

        # ★★★  核心改動：排進背景工作佇列  ★★★
        enqueue_planning(days, None, uid)

        safe_reply(replyTK, TextSendMessage(text=_t("please_wait", lang)), uid)
        return

    # 2-4 景點推薦 → 先詢問永續/一般
    if low in recommend_keys:
        yes_lbl     = _t("yes", lang)
        no_lbl      = _t("no", lang)
        payload_yes = "永續觀光" if lang == "zh" else "sustainable tourism"
        payload_no  = "一般景點推薦" if lang == "zh" else "general recommendation"
        tpl = ConfirmTemplate(
            text=_t("ask_sustainable", lang),
            actions=[
                MessageAction(label=yes_lbl, text=payload_yes),
                MessageAction(label=no_lbl,  text=payload_no),
            ]
        )
        safe_reply(
            replyTK,
            TemplateSendMessage(alt_text=_t("ask_sustainable", lang), template=tpl),
            uid
        )
        return

    # 2-5 永續 / 一般推薦
    if low in sustainable_keys:
        recommend_sustainable_places(replyTK, uid)
        return
    if low in general_keys:
        recommend_general_places(replyTK, uid)
        return

    # 2-6 附近搜尋：詢問關鍵字
    if low in nearby_keys:
        safe_reply(replyTK, FlexMessage.ask_keyword(), uid)
        return

    # 2-7 關鍵字搜尋（餐廳、停車場…）
    if is_keyword:
        kw = next((k for k, v in keyword_map.items() if v == low), text)
        search_nearby_places(replyTK, uid, kw)
        return

    # 2-8 租車
    if low in rental_keys:
        send_rental_car(replyTK, uid)
        return

    # 2-9 其他 → 不處理
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
    """處理單一事件，分發給 message 或 postback handler"""
    ev_type = ev.get("type")
    uid     = ev["source"]["userId"]
    lang    = shared.user_language.get(uid, 'zh')
    replyTK = ev.get("replyToken")

    if not replyTK:
        print("Warning: no reply token")
        return

    print(f"Handling event type: {ev_type}, user: {uid}, lang: {lang}")

    if ev_type == "postback":
        # 統一交給 handle_postback_event 處理
        handle_postback_event(ev, uid, lang, replyTK)
    elif ev_type == "message":
        handle_message_event(ev, uid, lang, replyTK)
    else:
        print(f"Unhandled event type: {ev_type}")

def handle_postback_event(ev, uid, lang, replyTK):
    """統一處理所有 Postback 事件"""
    data = ev["postback"]["data"]
    print(f"Postback data: {data}")

    # 1) 性別按鈕
    if data in ("男", "女", "其他"):
        handle_gender(uid, data, replyTK)
        return

    # 2) 天數按鈕
    if data in ("兩天一夜", "三天兩夜", "四天三夜", "五天四夜"):
        shared.user_trip_days[uid]  = data
        shared.user_preparing[uid]  = True
        shared.user_plan_ready[uid] = False
        shared.user_stage[uid]      = 'ready'

        # 先告知使用者「請稍候」，再把行程規劃排進佇列
        safe_reply(replyTK, TextSendMessage(text=_t("please_wait", lang)), uid)
        enqueue_planning(data, None, uid)
        return

    # 3) 系統路線／使用者路線按鈕
    sys_zh, usr_zh = "系統路線", "使用者路線"
    sys_en, usr_en = to_en(sys_zh), to_en(usr_zh)

    if data in (sys_zh, sys_en):
        try:
            lat, lon   = get_location.get_location(LOCATION_FILE)
            uid_qs     = urllib.parse.quote_plus(uid)
            url        = f"https://system-plan.eeddyytaddy.workers.dev/?uid={uid_qs}&lat={lat}&lng={lon}"
            safe_reply(replyTK, TextSendMessage(text=url), uid)
            shared.user_stage[uid] = 'ready'
        except Exception as e:
            print(f"Error getting location: {e}")
            safe_reply(replyTK, TextSendMessage(text=_t("cannot_get_location", lang)), uid)
        return

    if data in (usr_zh, usr_en):
        try:
            lat, lon   = get_location.get_location(LOCATION_FILE)
            uid_qs     = urllib.parse.quote_plus(uid)
            url        = f"https://user-plan.eeddyytaddy.workers.dev/?uid={uid_qs}&lat={lat}&lng={lon}"
            safe_reply(replyTK, TextSendMessage(text=url), uid)
            shared.user_stage[uid] = 'ready'
        except Exception as e:
            print(f"Error getting location: {e}")
            safe_reply(replyTK, TextSendMessage(text=_t("cannot_get_location", lang)), uid)
        return

    # 4) 其他 Postback 直接忽略
    print("Unhandled postback:", data)



from linebot.models import TextSendMessage, StickerSendMessage

# 在 app.py 開頭新增一個全域字典用於每個使用者的 Lock
user_event_lock = {}

def handle_message_event(ev, uid, lang, replyTK):
    """
    處理文字／位置／圖片／貼圖事件：
    0) 重啟資料收集流程
    1) 自由指令
    2) 階段流程：語言→年齡→性別→位置→天數→ready
    """
    # 使用者事件處理鎖定，確保同一使用者事件順序執行
    if uid not in user_event_lock:
        user_event_lock[uid] = threading.Lock()
    with user_event_lock[uid]:
        msg = ev.get("message", {})
        msgType = msg.get("type")
        text = (msg.get("text") or "").strip()
        low = text.lower()

        # —— 0) 重啟資料收集流程 ——
        if msgType == "text" and text.startswith("收集資料"):
            handle_ask_language(uid, replyTK)
            return

        # —— 1) 自由指令 ——
        crowd_keys  = {"景點人潮", "crowd analyzer", "3", "景點人潮(crowd analyzer)"}
        plan_keys   = {"行程規劃", "plan itinerary", "6", "行程規劃(itinerary planning)"}
        rec_keys    = {"景點推薦", "attraction recommendation", "2", "景點推薦(attraction recommendation)"}
        sust_keys   = {"永續觀光", "sustainable tourism", "2-1"}
        gen_keys    = {"一般景點推薦", "general recommendation", "2-2"}
        nearby_keys = {"附近搜尋", "nearby search", "4", "附近搜尋(nearby search)"}
        rental_keys = {"租車", "car rental information", "5", "租車(car rental information)"}
        keyword_map = {"餐廳": "restaurants", "停車場": "parking", "風景區": "scenic spots", "住宿": "accommodation"}
        is_keyword  = text in keyword_map or low in set(keyword_map.values())

        if msgType == "text":
            # Special handling for itinerary planning to prompt missing info
            if low in plan_keys:
                missing_field = None
                if shared.user_age.get(uid) is None:
                    missing_field = 'age'
                elif shared.user_gender.get(uid) is None:
                    missing_field = 'gender'
                elif shared.user_location.get(uid) is None:
                    missing_field = 'location'
                elif shared.user_trip_days.get(uid) is None:
                    missing_field = 'days'

                if missing_field:
                    # Prompt the user for the missing information
                    current_lang = _get_lang(uid)
                    if missing_field == 'age':
                        shared.user_stage[uid] = 'got_age'
                        safe_reply(replyTK, TextSendMessage(text=_t("ask_age", current_lang)), uid)
                    elif missing_field == 'gender':
                        shared.user_stage[uid] = 'got_gender'
                        handle_gender_buttons(uid, current_lang, replyTK)
                    elif missing_field == 'location':
                        shared.user_stage[uid] = 'got_location'
                        safe_reply(replyTK, FlexMessage.ask_location(), uid)
                    elif missing_field == 'days':
                        shared.user_stage[uid] = 'got_days'
                        # Prepare quick-reply options for trip duration
                        days_options = ["兩天一夜", "三天兩夜", "四天三夜", "五天四夜"]
                        qr_items = [
                            QuickReplyButton(
                                action=MessageAction(
                                    label=to_en(d) if current_lang == 'en' else d,
                                    text = to_en(d) if current_lang == 'en' else d
                                )
                            )
                            for d in days_options
                        ]
                        safe_reply(replyTK, TextSendMessage(text=_t("ask_days", current_lang),
                                                            quick_reply=QuickReply(items=qr_items)), uid)
                    return

                # All data collected, proceed to itinerary planning
                handle_free_command(uid, text, replyTK)
                return

            # Other free commands and keyword-based searches
            if (low in crowd_keys or low in rec_keys or low in sust_keys or 
                low in gen_keys or low in nearby_keys or low in rental_keys or is_keyword):
                handle_free_command(uid, text, replyTK)
                return

        # —— 2) 階段流程 ——
        stage = shared.user_stage.get(uid, 'ask_language')
        print(f"[Stage flow] type={msgType}, text={text}, stage={stage}")

        # 第一步：選擇語言
        if stage == 'ask_language' and msgType == "text":
            if low in ("中文", "zh", "english", "en"):
                handle_language(uid, text, replyTK)
            else:
                safe_reply(replyTK, TextSendMessage(text=_t("invalid_language", _get_lang(uid))), uid)
            return

        # **(Removed 'got_language' check – no longer needed)**

        # 第二步：輸入年齡
        if stage == 'got_age' and msgType == "text":
            handle_age(uid, text, replyTK)
            return
        # 第三步：處理性別
        if stage == 'got_gender' and msgType == "text":
            handle_gender(uid, text, replyTK)
            return

        # 第四步：處理位置（Location message）
        if stage == 'got_location' and msgType == "location":
            handle_location(uid, msg, replyTK)
            return

        # 第五步：處理天數
        if stage == 'got_days' and msgType == "text":
            handle_days(uid, text, replyTK)
            return

        # 第六步：Ready 階段的自由指令
        if stage == 'ready' and msgType == "text":
            handle_free_command(uid, text, replyTK)
            return

        # 處理圖片訊息
        if msgType == "image":
            safe_reply(replyTK, TextSendMessage(text=_t("data_fetch_failed", _get_lang(uid))), uid)
            return

        # 處理貼圖訊息
        if msgType == "sticker":
            safe_reply(replyTK, StickerSendMessage(package_id=msg.get("packageId"),
                                                   sticker_id=msg.get("stickerId")), uid)
            return

        # 其他類型的訊息不處理
        return




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
    from gevent import monkey;  monkey.patch_all()      # 確保先 patch
    from gevent.pywsgi import WSGIServer

    port = int(os.getenv("PORT", 10000))
    # backlog 設大一點避免 502，log=None 可省略存取 log 開銷
    http_server = WSGIServer(("0.0.0.0", port), app,
                             backlog=2048, log=None)
    print(f"🚀 gevent WSGI server started on :{port}")
    http_server.serve_forever()

# ---------------- END OF app.py ------------------------------------
