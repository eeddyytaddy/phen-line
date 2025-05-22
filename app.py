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

# Matplotlib 無頭模式
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.font_manager as fm
from matplotlib.patches import Patch
# 1. 先指定 font.family 為 'sans-serif'
plt.rcParams['font.family'] = 'sans-serif'

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
# ─────────────── Flask App ───────────────
app = Flask(__name__)

# LINE Bot 設定
ACCESS_TOKEN   = os.getenv("LINE_ACCESS_TOKEN",   "your_line_access_token_here")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "your_line_channel_secret_here")
line_bot_api   = LineBotApi(ACCESS_TOKEN)
handler        = WebhookHandler(CHANNEL_SECRET)
# 常數
#PHP_ngrok = "https://flask-service2.peterlinebot.ip-ddns.com"
PHP_NGROK       = "https://penghu-linebot-production.up.railway.app"
GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSeT7kHB3bsE7rmxqJdzG42XfSS9ewNBBZPVH3xxunpYVcyDag/viewform?usp=header"
GOOGLE_API_KEY  = os.getenv("GOOGLE_MAPS_API_KEY")
# ─────────────── 每-user 語系設定 & 其他全域狀態 ───────────────
from shared import user_language, user_stage


age_1                = None
gender_1             = None
trip_days            = None
preparing            = False
plan_ready           = False
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
def safe_reply(token, msgs):
    if not isinstance(msgs, list):
        msgs = [msgs]
    try:
        line_bot_api.reply_message(token, msgs)
    except Exception as e:
        print("safe_reply error:", e)

def safe_push(uid, msgs):
    if not isinstance(msgs, list):
        msgs = [msgs]
    try:
        line_bot_api.push_message(uid, msgs)
    except Exception as e:
        print("safe_push error:", e)

# ─────────────── 背景行程規劃 Thread ───────────────
def _background_planning(option, reply_token, user_id):
    global preparing, plan_ready
    try:
        process_travel_planning(option, reply_token, user_id)
        plan_ready = True
    except Exception as e:
        print("background planning failed:", e)
    finally:
        preparing = False
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
def update_plan_csv_with_populartimes(plan_csv_file, crowd_source="historical"):
    """
    在行程 CSV 加入 place_id、crowd（歷史平均 or 即時熱度）、distance_km，
    並先依距離再依人潮排序，再加 crowd_rank。
    
    - crowd_source: "historical" → 歷史平均 from daily_crowd_stats.csv
                    "realtime"   → 即時熱度 via get_current_popularity()
    """
    # 0. 如果要用歷史人潮，就先讀一次
    if crowd_source == "historical":
        avg_crowd = load_historical_avg_crowd()

    # 1. 讀取使用者定位
    loc_df = pd.read_csv(LOCATION_FILE, header=None,
                         usecols=[1,2], names=["lat","lng"])
    user_lat, user_lng = loc_df.iloc[0]
    user_loc = f"{user_lat},{user_lng}"

    # 2. 讀取並初始化行程 DataFrame
    df = pd.read_csv(plan_csv_file, encoding="utf-8-sig")
    for col, dv in (("place_id", ""), ("crowd", 0), ("crowd_rank", 0), ("distance_km", 0.0)):
        if col not in df.columns:
            df[col] = dv

    # 3. 建立 Google Maps Client
    gmaps = googlemaps.Client(key=GOOGLE_API_KEY)

    # 4. 逐筆查 place_id、套用人潮、計算距離
    for i, row in df.iterrows():
        place_name = row["設置點"]

        # (a) 查 place_id
        pid = ""
        try:
            res = gmaps.find_place(
                input=place_name,
                input_type="textquery",
                fields=["place_id"]
            )
            pid = res["candidates"][0]["place_id"]
        except Exception:
            pass
        df.at[i, "place_id"] = pid

        # (b) 根據 crowd_source 選擇人潮來源
        if crowd_source == "historical":
            df.at[i, "crowd"] = avg_crowd.get(place_name, 0)
        else:  # realtime
            df.at[i, "crowd"] = get_current_popularity(pid)

        # (c) 呼叫 Distance Matrix 計算距離
        distance_km = None
        try:
            matrix = gmaps.distance_matrix(
                origins=[user_loc],
                destinations=[f"place_id:{pid}"],
                mode="driving",
                units="metric"
            )
            elem = matrix["rows"][0]["elements"][0]
            if elem.get("status") == "OK":
                meters = elem["distance"]["value"]
                distance_km = round(meters / 1000, 3)
        except Exception:
            distance_km = None

        df.at[i, "distance_km"] = distance_km or 0.0

    # 5. 先依距離再依人潮排序
    df.sort_values(by=["distance_km", "crowd"], ascending=[True, True], inplace=True)

    # 6. 重新編排 crowd_rank
    df["crowd_rank"] = range(1, len(df) + 1)

    # 7. 寫回 CSV
    df.to_csv(plan_csv_file, index=False, encoding="utf-8-sig")



# === Part 1 END ===

# ---------- app.py  ※ Part 2 / 4  ----------------------------------
# ---- 1) XGBoost 排序 (Machine Learning) ----
@measure_time
def run_ml_sort(option, reply_token, user_id, df_plan):
    """
    以 XGBoost 依性別年齡做排序，回傳 userID list
    """
    return ML.XGboost_plan(df_plan, gender_1, age_1)


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
    根據熱門度、人潮數據進行再排序，並寫回 CSV
    """
    update_plan_csv_with_populartimes(plan_csv,crowd_source="realtime")


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
    拆成四段：ML → 過濾 → 重排 → 上傳，
    四段的時間都會被 measure_time 裝飾器分別記錄。
    """
    global age_1, gender_1
    # 檢查前置資料
    if gender_1 is None or age_1 is None:
        lang = _get_lang(user_id)   # 或 _get_lang(uid)
        safe_reply(reply_token, TextSendMessage(_t('collect_info', lang)))

        return

    # 讀入對應天數 CSV
    csv_path = {
        "兩天一夜": PLAN_2DAY,
        "三天兩夜": PLAN_3DAY,
        "四天三夜": PLAN_4DAY,
        "五天四夜": PLAN_5DAY
    }.get(option, PLAN_2DAY)

    try:
        df_plan = pd.read_csv(csv_path, encoding="utf-8-sig")
    except Exception as e:
        print("read CSV error:", e)
        lang = _get_lang(user_id)
        safe_push(user_id, TextSendMessage(_t('data_fetch_failed', lang)))
        return

    # 1) 排序
    try:
        userID = run_ml_sort(option, reply_token, user_id, df_plan)
    except Exception as e:
        print("XGboost_plan error:", e)
        lang = _get_lang(user_id)
        safe_push(user_id, TextSendMessage(_t('data_fetch_failed', lang)))
        return

    # 2) 過濾
    try:
        run_filter(option, reply_token, user_id, csv_path, userID)
    except Exception as e:
        print("filter error:", e)
        lang = _get_lang(user_id)
        safe_push(user_id, TextSendMessage(_t('data_fetch_failed', lang)))
        return

    # 3) 重排名
    try:
        run_ranking(option, reply_token, user_id, PLAN_CSV)
    except Exception as e:
        print("ranking error:", e)
        lang = _get_lang(user_id)
        safe_push(user_id, TextSendMessage(_t('data_fetch_failed', lang)))
        return

    # 4) 上傳
    try:
        run_upload(option, reply_token, user_id)
    except Exception as e:
        print("upload error:", e)
        lang = _get_lang(user_id)
        safe_push(user_id, TextSendMessage(_t('data_fetch_failed', lang)))
        return

    # 最後推送結果給使用者
    #safe_push(user_id, FlexMessage.show_plan(PLAN_CSV))



@measure_time
def people_high5(tk=None):
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
            safe_reply(tk, TextSendMessage(_t('data_fetch_failed')))
        return [], _t('data_fetch_failed')


def send_questionnaire(tk):
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
    ))

@measure_time
def send_crowd_analysis(tk):
    safe_reply(tk, [
        TextSendMessage("https://how-many-people.eeddyytaddy.workers.dev")
    ])


@measure_time
def recommend_general_places(tk, uid):
    lang = _get_lang(uid)
    try:
        # 1) 人潮前五
        dont_go, _ = people_high5()

        # 2) 天氣、溫度、潮汐 —— 都不带 timeout，直接调用
        try:
            raw_weather = Now_weather.weather()      # 可能返回 HTML or JSON 字符串
            print("轉換後的 JSON 資料 (weather):", raw_weather)
            w_str = raw_weather
        except Exception as e:
            print("Weather fetch error:", e)
            w_str = "晴"

        try:
            raw_temp = Now_weather.temperature()
            print("轉換後的 JSON 資料 (temperature):", raw_temp)
            t = float(raw_temp)
        except Exception as e:
            print("Temperature fetch error:", e)
            t = 25.0

        try:
            raw_tide = Now_weather.tidal()
            print("轉換後的 JSON 資料 (tidal):", raw_tide)
            tide = float(raw_tide)
        except Exception as e:
            print("Tidal fetch error:", e)
            tide = 0.0

        # 3) 模型推薦
        rec = XGBOOST_predicted.XGboost_recommend2(
            np.array([w_str]), gender_1 or -1, age_1 or 30, tide, t, dont_go
        )

        # 4) 產生 Flex Message
        website, img, maplink = PH_Attractions.Attractions_recommend(rec)

        # 5) 回覆
        msgs = [
            TextSendMessage(text=_t("system_recommend", lang)),
            TextSendMessage(text=rec),
            ImageSendMessage(
                original_content_url=f"{img}.jpg",
                preview_image_url   =f"{img}.jpg"
            ),
            TextSendMessage(text=website),
            TextSendMessage(text=maplink)
        ]
        safe_reply(tk, msgs)

    except Exception as e:
        print("❌ recommend_general_places overall error:", e)
        safe_reply(tk, TextSendMessage(text=_t('data_fetch_failed', lang)))
    return



@measure_time
def recommend_sustainable_places(tk, uid):
    lang = _get_lang(uid)

    try:
        # 1) 人潮前五
        dont_go, crowd_msg = people_high5()

        # 2) 天气 / 温度 / 潮汐
        try:
            raw_weather = Now_weather.weather()
        except:
            raw_weather = "晴"
        # —— 天氣映射：將小雨、中雨、大雨等對應到模型訓練過的「下雨」標籤 —— 
        weather_map = {
            '晴': '晴',
            '多雲': '多雲',
            '陰': '陰',
            '小雨': '下雨',
            '中雨': '下雨',
            '大雨': '下雨',
            '雷陣雨': '下雨',
            # 如有其他天氣描述，也可一併加入映射
        }
        w_str = weather_map.get(raw_weather, '晴')

        try:
            t = float(Now_weather.temperature() or 0)
        except:
            t = 25.0
        try:
            tide = float(Now_weather.tidal() or 0)
        except:
            tide = 0.0

        # 3) 模型推荐：若遇到 unseen label，就降級用「晴」
        try:
            rec = ML.XGboost_recommend3(
                np.array([w_str]), gender_1 or -1, age_1 or 30, tide, t, dont_go
            )
        except ValueError as e:
            print("❌ recommend_sustainable_places model error:", e)
            rec = ML.XGboost_recommend3(
                np.array(['晴']), gender_1 or -1, age_1 or 30, tide, t, dont_go
            )

        # 如果第一次結果在不去名單，再跑一次
        if rec in dont_go:
            rec = ML.XGboost_recommend3(
                np.array([w_str]), gender_1 or -1, age_1 or 30, tide, t, dont_go
            )

        # 4) 拿到 PH_Attractions 回的圖床字段
        web, img, maplink = PH_Attractions.Attractions_recommend1(rec)
        if "imgur.com" in img and not img.startswith("i.imgur.com"):
            _id = img.rstrip("/").split("/")[-1]
            img_url = f"https://i.imgur.com/{_id}.jpg"
        else:
            img_url = img if img.startswith(("http://", "https://")) else f"https://{img}.jpg"

        # 5) 构建并发送消息
        header = f"📊 {crowd_msg}"
        title  = to_en('永續觀光') if lang=='en' else '永續觀光'
        body   = f"{title}：{rec}\n{web}\n{maplink}"
        safe_reply(tk, [
            TextSendMessage(text=body),
            ImageSendMessage(
                original_content_url=img_url,
                preview_image_url=img_url
            )
        ])

    except Exception as e:
        print("❌ recommend_sustainable_places error:", e)
        safe_reply(tk, TextSendMessage(text=_t('data_fetch_failed', lang)))


@measure_time
def search_nearby_places(replyTK, uid, keyword):
    """
    根據關鍵字搜尋附近景點，並回傳多語 Carousel
    """
    # 1) 取 user 語系
    lang = _get_lang(uid)

    # 2) 取得使用者位置
    try:
        lat, lon = get_location.get_location(LOCATION_FILE)
    except Exception as e:
        print("get_location error:", e)
        safe_reply(replyTK, TextSendMessage(text=_t("cannot_get_location", lang)))
        return

    # 3) 呼叫 Google Maps Nearby Search
    try:
        Googlemap_function.googlemap_search_nearby(lat, lon, keyword)
    except Exception as e:
        print("googlemap_search_nearby error:", e)
        safe_reply(replyTK, TextSendMessage(text=_t("data_fetch_failed", lang)))
        return

    # 4) 產生 Carousel 內容（需要 uid）
    try:
        contents = FlexMessage.Carousel_contents(RECOMMEND_CSV, uid)
        carousel = FlexMessage.Carousel(contents, uid)
        safe_reply(replyTK, carousel)
    except Exception as e:
        print("Carousel generation error:", e)
        safe_reply(replyTK, TextSendMessage(text=_t("data_fetch_failed", lang)))

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
    ])


@measure_time
def handle_ask_language(uid, replyTK):
    """第一步：請使用者選擇語言"""
    prompt = _t("ask_language", "zh")
    qr = QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="中文(Chinese)", text="中文")),
        QuickReplyButton(action=MessageAction(label="英文(English)", text="English"))
    ])
    safe_reply(replyTK, TextSendMessage(text=prompt, quick_reply=qr))
    user_stage[uid] = 'got_language'

@measure_time
def handle_language(uid, text, replyTK):
    """第二步：處理語言選擇並詢問年齡"""
    low = text.lower()
    if low in ("中文", "zh"):
        user_language[uid] = "zh"
    elif low in ("english", "en"):
        user_language[uid] = "en"
    else:
        safe_reply(replyTK, TextSendMessage(text=_t("invalid_language", _get_lang(uid))))
        return
    safe_reply(replyTK, TextSendMessage(text=_t("ask_age", _get_lang(uid))))
    user_stage[uid] = 'got_age'

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
    safe_reply(replyTK, TemplateSendMessage(alt_text=_t("ask_gender", lang), template=tpl))
    user_stage[uid] = 'got_gender'

@measure_time
def handle_gender(uid, text, replyTK):
    """第四步：處理性別選擇並詢問位置"""
    ENG2ZH = {"Male": "男", "Female": "女", "Other": "其他"}
    zh_text = ENG2ZH.get(text, text)
    if zh_text not in ("男", "女", "其他"):
        safe_reply(replyTK, TextSendMessage(text=_t("invalid_gender", _get_lang(uid))))
        return
    global gender_1
    gender_1 = FlexMessage.classify_gender(zh_text)
    safe_reply(replyTK, FlexMessage.ask_location())
    user_stage[uid] = 'got_location'

@measure_time
def handle_location(uid, msg, replyTK):
    """第五步：處理位置訊息並顯示天數選擇"""
    addr, lat, lon = msg["address"], msg["latitude"], msg["longitude"]
    with open(LOCATION_FILE, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([addr, lat, lon])
    days = ["兩天一夜", "三天兩夜", "四天三夜", "五天四夜"]
    lang = _get_lang(uid)
    qr_items = [
        QuickReplyButton(action=MessageAction(
            label=to_en(d) if lang=='en' else d,
            text =to_en(d) if lang=='en' else d
        ))
        for d in days
    ]
    safe_reply(replyTK, TextSendMessage(
        text=_t("position_saved", lang),
        quick_reply=QuickReply(items=qr_items)
    ))
    user_stage[uid] = 'got_days'

@measure_time
def handle_days(uid, text, replyTK):
    """第六步：處理天數選擇並啟動行程規劃"""
    zh_days = ["兩天一夜", "三天兩夜", "四天三夜", "五天四夜"]
    eng2zh  = {to_en(d): d for d in zh_days}
    lang = _get_lang(uid)
    choice = eng2zh.get(text, text)
    if choice not in zh_days:
        safe_reply(replyTK, TextSendMessage(text=_t("invalid_days", lang)))
        return
    global trip_days, preparing, plan_ready
    trip_days = choice
    preparing, plan_ready = True, False
    user_stage[uid] = 'ready'
    threading.Thread(
        target=_background_planning,
        args=(trip_days, replyTK, uid),
        daemon=True
    ).start()
    safe_reply(replyTK, TextSendMessage(text=_t("please_wait", lang)))

def handle_free_command(uid, text, replyTK):
    """
    Ready 階段的自由指令處理：
    包含「收集資料」「景點人潮」「行程規劃」「景點推薦」「永續觀光」
    「附近搜尋」「關鍵字搜尋」「租車」等指令。
    """
    from linebot.models import (
        TextSendMessage, TemplateSendMessage, ConfirmTemplate,
        QuickReply, QuickReplyButton, MessageAction, StickerSendMessage
    )
    # 若需呼叫 push，記得 import safe_push、FlexMessage.ask_route_option(), TextSendMessage, FlexMessage.ask_keyword 等
    low = text.lower()
    lang = _get_lang(uid)
    global preparing, plan_ready, trip_days

    # 指令集合
    recollect_keys    = {
                "收集資料&修改資料", "收集資料&修改資料(data collection)",
                "data collection", "collect data", "1"
            }
    crowd_keys        = {
                "景點人潮", "景點人潮(crowd analyzer)",
                "crowd analyzer", "crowd analysis", "crowd info", "3"
            }
    plan_keys         = {
                "行程規劃", "行程規劃(itinerary planning)",
                "itinerary planning", "plan itinerary", "6"
            }
    recommend_keys    = {
                "景點推薦", "景點推薦(attraction recommendation)",
                "attraction recommendation", "recommend spot", "2"
            }
    sustainable_keys  = {
                "永續觀光", "永續觀光(sustainable tourism)",
                "sustainable tourism", "2-1"
            }
    general_keys      = {
                "一般景點推薦", "一般景點推薦(general recommendation)",
                "general recommendation", "2-2"
            }
    nearby_keys       = {
                "附近搜尋", "附近搜尋(nearby search)",
                "nearby search", "4"
            }
    rental_keys       = {
                "租車", "租車(car rental information)",
                "car rental information", "car rental", "5"
            }
    keyword_map = {
                "餐廳": "restaurants",
                "停車場": "parking",
                "風景區": "scenic spots",
                "住宿": "accommodation"
            }

    # 1) 收集資料：回到選語言
    if low in recollect_keys:
        prompt = _t("ask_language", "zh")
        qr = QuickReply(items=[
            QuickReplyButton(action=MessageAction(label="中文(Chinese)", text="中文")),
            QuickReplyButton(action=MessageAction(label="英文(English)", text="English"))
        ])
        safe_reply(replyTK, TextSendMessage(text=prompt, quick_reply=qr))
        user_stage[uid] = 'got_language'
        return

    # 2) 景點人潮
    if low in crowd_keys:
        send_crowd_analysis(replyTK)
        return

    # 3) 行程規劃
    if low in plan_keys:
        if preparing:
            safe_reply(replyTK, TextSendMessage(text=_t("prep_in_progress", lang)))
        elif plan_ready:
            # 系統說明與使用者說明同 linebot_route
            if lang == 'en':
                days_label = to_en(trip_days)
                desc1 = f"Using machine learning based on relevance, we found the best {days_label} itinerary for you"
            else:
                desc1 = f"以機器學習依據相關性，找尋過往數據最適合您的{trip_days}行程"

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
                    '1. Tap "Add to route" to include in list.\n'
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

            safe_push(uid, [
                FlexMessage.ask_route_option(),
                TextSendMessage(text=desc1),
                TextSendMessage(text=desc_sys),
                TextSendMessage(text=desc_usr),
            ])
        else:
            safe_reply(replyTK, TextSendMessage(text=_t("collect_info", lang)))
        return

    # 4) 景點推薦（先問是否永續）
    if low in recommend_keys:
        yes_lbl = _t("yes", lang); no_lbl = _t("no", lang)
        payload_yes = "永續觀光" if lang=='zh' else "sustainable tourism"
        payload_no  = "一般景點推薦" if lang=='zh' else "general recommendation"
        tpl = ConfirmTemplate(
            text=_t("ask_sustainable", lang),
            actions=[
                MessageAction(label=yes_lbl, text=payload_yes),
                MessageAction(label=no_lbl,  text=payload_no)
            ]
        )
        safe_reply(replyTK, TemplateSendMessage(alt_text=_t("ask_sustainable", lang), template=tpl))
        return

    # 5) 永續觀光 / 一般推薦
    if low in sustainable_keys:
        recommend_sustainable_places(replyTK, uid)
        return
    if low in general_keys:
        recommend_general_places(replyTK, uid)
        return

    # 6) 附近搜尋
    if low in nearby_keys:
        safe_reply(replyTK, FlexMessage.ask_keyword())
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

    # 9) 其他都忽略
    return


# ========== LINE 主路由 ========== #
@app.route("/", methods=["POST"])
def linebot_route():
    global age_1, gender_1, trip_days, preparing, plan_ready

    body    = request.get_json(silent=True) or {}
    events  = body.get("events", [])
    if not events:
        return "OK"

    ev      = events[0]
    ev_type = ev.get("type")
    uid     = ev["source"]["userId"]
    lang    = _get_lang(uid)
    stage   = user_stage.get(uid, 'ask_language')
    replyTK = ev.get("replyToken")

    # 1) PostbackEvent：只處理按鈕
    if ev_type == "postback":
        data = ev["postback"]["data"]

        # 性別按鈕
        if data in ("男", "女", "其他"):
            handle_gender(uid, data, replyTK)
            return "OK"

        # 行程天數按鈕
        if data in ("兩天一夜", "三天兩夜", "四天三夜", "五天四夜"):
            preparing, plan_ready = True, False
            trip_days = data
            user_stage[uid] = 'ready'
            threading.Thread(
                target=_background_planning,
                args=(data, replyTK, uid),
                daemon=True
            ).start()
            safe_reply(replyTK, TextSendMessage(text=_t("please_wait", lang)))
            return "OK"

        # 系統路線 / 使用者路線
        sys_zh, usr_zh = "系統路線", "使用者路線"
        sys_en, usr_en = to_en(sys_zh), to_en(usr_zh)
        if data in (sys_zh, sys_en):
            lat, lon = get_location.get_location(LOCATION_FILE)
            safe_reply(replyTK, TextSendMessage(
                text=f"https://system-plan…?lat={lat}&lng={lon}"
            ))
            user_stage[uid] = 'ready'
            return "OK"
        if data in (usr_zh, usr_en):
            lat, lon = get_location.get_location(LOCATION_FILE)
            safe_reply(replyTK, TextSendMessage(
                text=f"https://user-plan…?lat={lat}&lng={lon}"
            ))
            user_stage[uid] = 'ready'
            return "OK"

        return "OK"

    # 2) MessageEvent：階段式對話 + 自由指令
    elif ev_type == "message":
        msg     = ev["message"]
        msgType = msg.get("type")
        text    = (msg.get("text") or "").strip()
        # 2.1 請選語言
        if stage == 'ask_language' and msgType == "text":
            handle_ask_language(uid, replyTK)
            return "OK"

        # 2.2 收到語言後請輸入年齡
        if stage == 'got_language' and msgType == "text":
            handle_language(uid, text, replyTK)
            return "OK"

        # 2.3 年齡回覆
        if stage == 'got_age' and msgType == "text":
            try:
                age = int(text)
                if 0 <= age <= 120:
                    age_1 = age
                    handle_gender_buttons(uid, lang, replyTK)
                else:
                    safe_reply(replyTK, TextSendMessage(text=_t("enter_valid_age", lang)))
            except:
                safe_reply(replyTK, TextSendMessage(text=_t("enter_number", lang)))
            return "OK"

        # 2.4 性別回覆
        if stage == 'got_gender' and msgType == "text":
            handle_gender(uid, text, replyTK)
            return "OK"

        # 2.5 位置訊息
        if stage == 'got_location' and msgType == "location":
            handle_location(uid, msg, replyTK)
            return "OK"

        # 2.6 天數選擇
        if stage == 'got_days' and msgType == "text":
            handle_days(uid, text, replyTK)
            return "OK"

        # 2.7 Ready 階段：自由指令
        if stage == 'ready' and msgType == "text":
            handle_free_command(uid, text, replyTK)
            return "OK"

        # 圖片／貼圖
        if msgType == "image":
            safe_reply(replyTK, TextSendMessage(text=_t("data_fetch_failed", lang)))
            return "OK"
        if msgType == "sticker":
            safe_reply(replyTK, StickerSendMessage(
                package_id=msg["packageId"], sticker_id=msg["stickerId"]
            ))
            return "OK"

        return "OK"

    # 3) 其它事件
    else:
        return "OK"


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
        safe_reply(tk, FlexMessage.ask_location())
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
        safe_reply(tk, TextSendMessage(text=_t("please_wait", lang)))
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
            safe_reply(tk, TextSendMessage(text=url))
        except:
            safe_reply(tk, TextSendMessage(text=_t("cannot_get_location", lang)))
        user_stage[uid] = 'ready'
        return

    if data in valid_usr:
        try:
            lat, lon = get_location.get_location(LOCATION_FILE)
            url = f"https://user-plan.eeddyytaddy.workers.dev?lat={lat}&lng={lon}"
            safe_reply(tk, TextSendMessage(text=url))
        except:
            safe_reply(tk, TextSendMessage(text=_t("cannot_get_location", lang)))
        user_stage[uid] = 'ready'
        return

    # 其餘 Postback 直接忽略
    print("Unhandled postback:", data)

# === Part 3 END ===
# ---------- app.py  ※ Part 4 / 4  ----------------------------------
# === 即時圖表 Endpoints ============================================ #
@app.route("/metrics/runtime_bar.png")
def runtime_bar_png():
    import io
    import matplotlib.pyplot as plt
    from collections import OrderedDict

    # 1. 讀取原始長格式資料
    df = fetch_data(hours=24).reset_index()   # ts, fn, duration_ms

    # 2. 計算每支函式的總耗時 (ms → s)
    dur_s = (
        df.groupby("fn")["duration_ms"]
          .sum()
          .div(1000.0)
    )

    # 3. 「Data Collection」五支函式改用平均，不再累加
    initial_keys = [
        "handle_ask_language",
        "handle_language",
        "handle_gender_buttons",
        "handle_gender",
        "handle_location",
    ]
    dur_s["collect_user_data"] = dur_s.reindex(initial_keys, fill_value=0.0).mean()

    # 4. 對其他「需要合併前綴」做一次累加
    def collapse(prefix, new_key):
        matches = [fn for fn in dur_s.index if fn.startswith(prefix)]
        dur_s[new_key] = dur_s.reindex(matches, fill_value=0.0).sum()

    collapse("search_nearby_places",           "search_nearby_places")
    collapse("process_travel_planning",        "process_travel_planning")
    collapse("recommend_general_places",       "recommend_general_places")
    collapse("recommend_sustainable_places",    "recommend_general_places")
    collapse("send_crowd_analysis",            "send_crowd_analysis")
    collapse("send_rental_car",                "send_rental_car")

    # 5. 定義顯示順序與標籤
    label_map = OrderedDict([
        ("collect_user_data",          "Data Collection"),
        ("recommend_general_places",   "Attraction Recommendation"),
        ("process_travel_planning",    "Itinerary Planning"),
        ("send_crowd_analysis",        "Crowd Information"),
        ("search_nearby_places",       "Nearby Search"),
        ("send_rental_car",            "Car Rental Information"),
    ])

    # 6. 只保留這些欄位，缺少補 0
    final_s       = dur_s.reindex(label_map.keys(), fill_value=0.0)
    display_names = list(label_map.values())
    values        = final_s.values

    # 7. 配色
    cmap = plt.get_cmap("tab10").colors
    color_map = {
        "Data Collection":           cmap[9],
        "Attraction Recommendation": cmap[8],
        "Itinerary Planning":        cmap[6],
        "Crowd Information":         cmap[4],
        "Nearby Search":             cmap[2],
        "Car Rental Information":    cmap[0],
    }
    bar_colors = [color_map[name] for name in display_names]

    # 8. 繪製水平長條圖
    buf = io.BytesIO()
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.barh(display_names, values, color=bar_colors, height=0.6)

    # 9. 標注數值
    max_val = max(values.max(), 1e-6)
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_width() + max_val * 0.005,
            bar.get_y() + bar.get_height()/2,
            f"{val:.2f}s",
            va="center", fontsize=12
        )

    # 10. 美化
    ax.set_xlabel("Time (s)", fontsize=12)
    ax.set_xlim(0, max_val * 1.05)
    ax.grid(axis="x", linestyle="--", alpha=0.3)
    ax.invert_yaxis()
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)

    # 11. 標題
    fig.text(0.5, 0.02, "Execution Time of Each Function", ha="center", fontsize=14)

    fig.tight_layout(rect=[0,0.05,1,1])
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return send_file(buf, mimetype="image/png")




@app.route("/metrics/stacked_runtime_by_cmd.png")
def stacked_runtime_by_cmd_png():
    import io
    import pandas as pd
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    # 1) 拿到 ts, fn, duration_ms
    df = fetch_data(hours=24).reset_index()
    # 2) 每 10 分鐘 & 每個 fn 平均
    df = df.groupby([pd.Grouper(key='ts', freq='10min'), 'fn'])['duration_ms'] \
           .mean() \
           .reset_index()

    # 3) 定義各指令對應的函式名稱
    CMD_FN = {
        '兩天一夜': ['process_travel_planning_兩天一夜',
                     'update_plan_csv_with_populartimes_兩天一夜',
                     'get_current_popularity_兩天一夜'],
        '三天兩夜': ['process_travel_planning_三天兩夜',
                     'update_plan_csv_with_populartimes_三天兩夜',
                     'get_current_popularity_三天兩夜'],
        '四天三夜': ['process_travel_planning_四天三夜',
                     'update_plan_csv_with_populartimes_四天三夜',
                     'get_current_popularity_四天三夜'],
        '五天四夜': ['process_travel_planning_五天四夜',
                     'update_plan_csv_with_populartimes_五天四夜',
                     'get_current_popularity_五天四夜'],
        '一般景點推薦': ['recommend_general_places', 'people_high5'],
        '永續觀光':     ['recommend_sustainable_places', 'people_high5'],
        '附近搜尋':     ['search_nearby_places', 'people_high5']
    }

    # 4) 計算每個指令每支函式的平均秒數
    cmd_avg = {
        cmd: [df.loc[df['fn'] == fn, 'duration_ms'].mean() / 1000.0
              for fn in fns]
        for cmd, fns in CMD_FN.items()
    }

    # 5) 準備顏色映射
    funcs = list({fn for fns in CMD_FN.values() for fn in fns})
    cmap = plt.get_cmap('tab10').colors
    color_map = {fn: cmap[i % len(cmap)] for i, fn in enumerate(funcs)}

    # 6) 繪圖
    buf = io.BytesIO()
    fig, ax = plt.subplots(figsize=(12, 6))
    x = range(len(CMD_FN))
    bottom = [0] * len(CMD_FN)

    for i, (cmd, fns) in enumerate(CMD_FN.items()):
        heights = [cmd_avg[cmd][j] or 0 for j in range(len(fns))]
        ax.bar(
            i, heights,
            bottom=bottom[i],
            color=[color_map[fn] for fn in fns],
            width=0.6
        )
        bottom[i] += sum(heights)

    ax.set_xticks(list(x))
    ax.set_xticklabels(
        [to_en(cmd) if user_language == 'en' else cmd for cmd in CMD_FN.keys()],
        rotation=25, ha='right'
    )
    ax.set_ylabel("Avg Runtime (s)")

    # 7) 正確呼叫 legend(handles, labels)
    handles = [Patch(color=color_map[fn], label=fn) for fn in funcs]
    labels = funcs
    ax.legend(
        handles, labels,
        title="Function",
        bbox_to_anchor=(1.05, 1),
        loc='upper left',
        fontsize=8
    )

    fig.tight_layout(rect=[0, 0, 0.8, 1])
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/metrics/itinerary_stacked.png")
def itinerary_stacked_png():
    import io
    import pandas as pd
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    # 0) 配置字體與減號支持
    plt.rcParams['font.family'] = 'DejaVu Sans'
    plt.rcParams['axes.unicode_minus'] = True

    # 1) 取出過去 24h 的記錄
    df = fetch_data(hours=24).reset_index()  # ts, fn, duration_ms

    # 2) 每 10 分鐘 & 每個 fn 平均耗時 (ms → s)
    df = (
        df
        .groupby([pd.Grouper(key='ts', freq='10min'), 'fn'])['duration_ms']
        .mean()
        .reset_index()
    )
    fn_avg_s = df.groupby('fn')['duration_ms'].mean().div(1000.0)

    # 3) 四個子流程對應的函式清單
    CMD_FN = {
        '2days': [
            'run_ml_sort_兩天一夜',
            'run_filter_兩天一夜',
            'run_ranking_兩天一夜',
            'save_to_sqlite_兩天一夜',
        ],
        '3days': [
            'run_ml_sort_三天兩夜',
            'run_filter_三天兩夜',
            'run_ranking_三天兩夜',
            'save_to_sqlite_三天兩夜',
        ],
        '4days': [
            'run_ml_sort_四天三夜',
            'run_filter_四天三夜',
            'run_ranking_四天三夜',
            'save_to_sqlite_四天三夜',
        ],
        '5days': [
            'run_ml_sort_五天四夜',
            'run_filter_五天四夜',
            'run_ranking_五天四夜',
            'save_to_sqlite_五天四夜',
        ],
    }

    # 4) 構造每個 cmd 的四段耗時列表，fn 若不存在則補 0
    cmd_avg = {
        cmd: [fn_avg_s.get(fn, 0.0) for fn in fns]
        for cmd, fns in CMD_FN.items()
    }

    # 5) 色盤：tab10 中 0=藍, 3=紅, 6=粉, 9=青
    cmap = plt.get_cmap('tab10').colors
    color_map = {
        'run_ml_sort': cmap[0],
        'run_filter': cmap[3],
        'run_ranking': cmap[6],
        'save_to_sqlite': cmap[9],
    }
    get_color = lambda fn: next(
        (col for prefix, col in color_map.items() if fn.startswith(prefix)),
        'gray'
    )

    # 6) 繪圖並標註
    buf = io.BytesIO()
    fig, ax = plt.subplots(figsize=(12, 6))
    y_pos = list(range(len(CMD_FN)))

    # 計算每條總長度的最大值，用於最後留邊
    max_total = max(sum(cmd_avg[cmd]) for cmd in CMD_FN)

    # 標籤門檻設定（秒）
    threshold_center = 0.5    # ≥0.5s 置中白字
    threshold_external = 0.1  # ≥0.1s 外置黑字，小於此就不顯示

    for i, (cmd, fns) in enumerate(CMD_FN.items()):
        widths = cmd_avg[cmd]
        left = 0
        for fn, w in zip(fns, widths):
            col = get_color(fn)
            ax.barh(i, w, left=left, height=0.6, color=col)
            label = f"{w:.2f}s"

            if w >= threshold_center:
                # 置中顯示白色標籤
                ax.text(
                    left + w/2, i, label,
                    va='center', ha='center',
                    fontsize=12, color='white',
                    clip_on=False
                )
            elif w >= threshold_external:
                # 外置顯示黑色標籤
                ax.text(
                    left + w + 0.02, i, label,
                    va='center', ha='left',
                    fontsize=12, color='black',
                    clip_on=False
                )
            # else: 太小不顯示標籤

            left += w

    # 7) 坐標與網格
    ax.set_yticks(y_pos)
    ax.set_yticklabels(list(CMD_FN.keys()), fontsize=14)
    ax.set_xlabel("Time (s)", fontsize=14)
    ax.grid(axis="x", linestyle="--", alpha=0.3)
    ax.invert_yaxis()
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    # 多留 0.5s 的空間給右側標籤
    ax.set_xlim(0, max_total + 0.5)

    # 8) 圖例
    legend_handles = [
        Patch(color=cmap[0], label="Machine Learning"),
        Patch(color=cmap[3], label="Attraction Filtering"),
        Patch(color=cmap[6], label="Attraction Ranking"),
        Patch(color=cmap[9], label="Data to Database"),
    ]
    ax.legend(
        handles=legend_handles,
        title="Sub-function",
        title_fontsize=12,
        fontsize=12,
        bbox_to_anchor=(1.05, 0.5),
        loc='center left'
    )

    # 9) 底部副標題
    fig.text(
        0.5, 0.02,
        "(b) Itinerary Planning Function (Using Historical Crowd Data)",
        ha='center', fontsize=16
    )

    # 10) 輸出圖片
    fig.tight_layout(rect=[0, 0.05, 1, 1])
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return send_file(buf, mimetype="image/png")



# ================= MAIN =========================================== #
if __name__ == "__main__":
    print("🚀 Flask server start …")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",8000)), debug=True)

# ---------------- END OF app.py ------------------------------------
