# app.py 
from gevent import monkey
monkey.patch_all()
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
import random
from collections import Counter
from zh2en import TEXTS as I18N, to_en ,ZH2EN
from flask import Flask, request, jsonify, send_file, render_template
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
    LOCATION_FILE, RECOMMEND_CSV, OUT_PUT
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
# --- 應用程式路由定義 ---

# 明確指定接受 GET 請求
@app.route('/', methods=['GET'])
def index():
    """
    處理首頁路由 (/)，並渲染 templates/index.html。
    這裡可以傳遞動態資料到模板中。
    """
    # 範例動態資料：將環境變數傳遞給 HTML 模板
    dynamic_data = {
        'title': '探尋世界的角落',
        'env': os.environ.get('APP_ENV', 'Local Development')
    }
    
    # Flask 會自動在 'templates' 資料夾中尋找 index.html
    return render_template('index.html', data=dynamic_data)

@app.route('/healthz')
def health_check():
    """
    健康檢查端點，供 Dockerfile 和 K8s 使用。
    """
    return "OK", 200

# 只有在本地執行 (非 Gunicorn) 時才啟用
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    # 運行在 0.0.0.0 確保容器內外部可訪問
    app.run(host='0.0.0.0', port=port, debug=True)

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
def _get_identity_gender_for_tamsui(uid: str):
    """
    從 shared 拿使用者「是否為學生」與「中文性別」，
    轉成淡水 XGBoost 模型需要的 Identity / Gender 字串。
    """
    # 1) 身分：根據你訓練資料 Identity 欄位使用的字
    is_student = shared.user_student.get(uid)

    if is_student is True:
        identity = "Student"
    elif is_student is False:
        identity = "Non-Student"    # 如果你訓練資料不是用 Worker，請改成一樣的字
    else:
        identity = "Other"     # 沒回答就當 Other，避免丟 None 出去

    # 2) 性別：把中文轉成英文（要跟訓練資料 Gender 欄位一致）
    raw_gender = shared.user_gender.get(uid, "")
    gender_map = {
        "男": "Male",
        "女": "Female",
        "其他": "Other",
    }
    gender = gender_map.get(raw_gender, "Other")

    return identity, gender


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

def apply_tamsui_xgb_to_plan(user_id: str, plan_csv_path: str):
    """
    使用淡水 XGBoost (XGBOOST_predicted.predict_preference)
    依 Identity + Gender 對景點預測評分，
    然後把結果寫回行程 CSV 重新排序。

    ⚠️ 不動學姊原本的 ML / Filter / ranking，只是在兩者中間多一層排序。
    """
    # 1) 從 shared 轉成模型需要的 Identity / Gender
    identity, gender = _get_identity_gender_for_tamsui(user_id)

    try:
        # 2) 呼叫你提供的 predict_preference
        #    （你 app.py 一開始已經有 import XGBOOST_predicted）
        results = XGBOOST_predicted.predict_preference(identity, gender)
    except Exception as e:
        print(f"[tamsui_xgb] predict_preference 呼叫失敗: {e}")
        return

    # 3) 如果回傳的是錯誤訊息（字串），就直接跳過，不影響原本流程
    if isinstance(results, str):
        print(f"[tamsui_xgb] 預測失敗訊息: {results}")
        return

    # 期待 results 是一個 DataFrame，欄位：'景點 (Attraction)'、'預測評分 (Predicted Rating)'
    if "景點 (Attraction)" not in results.columns:
        print("[tamsui_xgb] 結果中沒有『景點 (Attraction)』欄位，略過淡水 XGB 排序")
        return

    ranked_attrs = results["景點 (Attraction)"].tolist()  # 由高到低排序好的景點名稱（英文）

    # 4) 讀取目前的行程 CSV
    try:
        df = pd.read_csv(plan_csv_path, encoding="utf-8-sig")
    except Exception as e:
        print(f"[tamsui_xgb] 讀取 {plan_csv_path} 失敗: {e}")
        return

    # 5) 找一個欄位可以跟 XGBoost 的景點名稱對應
    #   你可以依實際 CSV 欄位名微調。這裡做一個自動判斷：
    candidate_cols = [
        "Attraction",          # 如果你有英文景點欄
        "景點 (Attraction)",   # 也可能你就是用這個欄名
        "景點英文"             # 或其他你之後想用的欄名
    ]
    attr_col = None
    for col in candidate_cols:
        if col in df.columns:
            attr_col = col
            break

    if not attr_col:
        print(f"[tamsui_xgb] 在 {plan_csv_path} 找不到可以對應景點的欄位，略過淡水 XGB 排序")
        return

    # 6) 根據 XGBoost 給的 ranking 對 CSV 重新排序
    def get_rank(name):
        try:
            return ranked_attrs.index(name)
        except ValueError:
            # 找不到的景點統一排在最後
            return len(ranked_attrs)

    df["tamsui_xgb_rank"] = df[attr_col].apply(get_rank)
    df.sort_values(by="tamsui_xgb_rank", inplace=True)
    df.drop(columns=["tamsui_xgb_rank"], inplace=True)

    # 7) 寫回原本 CSV（覆寫）
    try:
        df.to_csv(plan_csv_path, index=False, encoding="utf-8-sig")
        print(f"[tamsui_xgb] 已根據淡水 XGBoost 重新排序並寫回: {plan_csv_path}")
    except Exception as e:
        print(f"[tamsui_xgb] 寫回 {plan_csv_path} 失敗: {e}")

@measure_time
def recommend_best_tamsui_spot(replyTK, uid):
    """
    直接使用淡水 XGBoost，根據使用者 Identity + Gender
    算出對 6 個景點的預測評分：
      1) 呼叫 XGBOOST_predicted.predict_preference
      2) 輸出完整結果到 OUT_PUT CSV
      3) 把最高分那一個景點名稱 + 網址推播給使用者
    """
    lang = _get_lang(uid)

    # 1) 轉成模型需要的 Identity / Gender 字串
    identity, gender = _get_identity_gender_for_tamsui(uid)

    try:
        results = XGBOOST_predicted.predict_preference(identity, gender)
    except Exception as e:
        print(f"[tamsui_best] predict_preference error: {e}")
        safe_reply(replyTK, TextSendMessage(text=_t('data_fetch_failed', lang)), uid)
        return

    # 2) 如果回傳的是錯誤訊息（字串），直接回給使用者
    if isinstance(results, str):
        print(f"[tamsui_best] model message: {results}")
        safe_reply(replyTK, TextSendMessage(text=results), uid)
        return

    # 3) 安全檢查欄位
    if "景點 (Attraction)" not in results.columns or "預測評分 (Predicted Rating)" not in results.columns:
        print("[tamsui_best] invalid result columns:", results.columns)
        safe_reply(replyTK, TextSendMessage(text=_t('data_fetch_failed', lang)), uid)
        return

    # 4) 把結果輸出到 CSV（滿足你說的「結果 CSV」）
    try:
        results.to_csv(OUT_PUT, index=False, encoding="utf-8-sig")
        print(f"[tamsui_best] results saved to {OUT_PUT}")
    except Exception as e:
        print(f"[tamsui_best] save csv failed: {e}")
        # 就算存檔失敗，我們仍然可以用 DataFrame 本身繼續玩

    # 5) 取最高分那一筆
    top_row = results.iloc[0]
    attr_en = str(top_row["景點 (Attraction)"])
    score   = float(top_row["預測評分 (Predicted Rating)"])

    # 6) 根據英文景點名稱找到中文名稱 + 網址
    zh_name, url = TAMSUI_ATTR_INFO.get(attr_en, (attr_en, None))

    # 7) 組訊息文字（中英雙語處理）
    if lang == "zh":
        title = f"根據您的身分與性別，最適合您的淡水景點是：{zh_name}"
        detail = f"模型預測評分：{score:.2f}\n英文名稱：{attr_en}"
        if url:
            tail = f"\n\n詳細介紹請見：\n{url}"
        else:
            tail = ""
        text = f"{title}\n{detail}{tail}"
    else:
        title = f"Based on your profile, the best-matched spot in Tamsui is: {attr_en}"
        detail = f"Predicted rating: {score:.2f}\nChinese name: {zh_name}"
        if url:
            tail = f"\n\nMore info:\n{url}"
        else:
            tail = ""
        text = f"{title}\n{detail}{tail}"

    safe_reply(replyTK, TextSendMessage(text=text), uid)



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

     # 淡水 XGBoost 偏好排序（新增步驟，不動原本程式）
    try:
        # 這裡假設 Filter.filter 的輸出行程 CSV 是寫到 PLAN_CSV
        # 如果實際上是寫回 csv_path，就把 PLAN_CSV 改成 csv_path
        apply_tamsui_xgb_to_plan(user_id, PLAN_CSV)
    except Exception as e:
        print(f"[tamsui_xgb] apply_tamsui_xgb_to_plan error: {e}")
        # 不 return，讓原本 ranking / upload 照跑

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
        TextSendMessage("https://phen-line-547744493031.asia-east1.run.app/")
    ],uid)

# 固定的餐廳/景點清單（我要的 6 個點）
PLACE_URLS = {
    "淡水老街": "https://newtaipei.travel/zh-tw/attractions/detail/109658",
    "漁人碼頭": "https://newtaipei.travel/zh-tw/attractions/detail/109659",
    "金色水岸": "https://newtaipei.travel/zh-tw/attractions/detail/209657",
    "滬尾砲台": "https://newtaipei.travel/zh-tw/attractions/detail/110398",
    "紅毛城":   "https://newtaipei.travel/zh-tw/attractions/detail/109672",
    "沙崙海灘": "https://egoldenyears.com/92435/",
}

# 🔗 XGBoost 英文景點名稱 → (中文名稱, 對應網址)
TAMSUI_ATTR_INFO = {
    "Fort San Domingo":      ("紅毛城",     PLACE_URLS["紅毛城"]),
    "Tamsui Old Street":     ("淡水老街",   PLACE_URLS["淡水老街"]),
    "Tamshui Gold Seashore": ("金色水岸",   PLACE_URLS["金色水岸"]),
    "Hobe Fort":             ("滬尾砲台",   PLACE_URLS["滬尾砲台"]),
    "Fisherman's Wharf":     ("漁人碼頭",   PLACE_URLS["漁人碼頭"]),
    "Shalun Beach":          ("沙崙海灘",   PLACE_URLS["沙崙海灘"]),
}

# ✅ 代號對應表（1～6）
PLACE_CODES = {
    "1": "淡水老街",
    "2": "漁人碼頭",
    "3": "金色水岸",
    "4": "滬尾砲台",
    "5": "紅毛城",
    "6": "沙崙海灘",
}
# 🔹固定的餐廳網址（我提供的 18 個）
RESTAURANT_URLS = [
    "https://maps.app.goo.gl/vixH7xDGPFE2oCsR7?g_st=ipc",
    "https://maps.app.goo.gl/d4hbj6oyGbRm8kLw5?g_st=ipc",
    "https://maps.app.goo.gl/rzt2zBBVP5451rKK9?g_st=ipc",
    "https://maps.app.goo.gl/mLdSMS16V7htFrFC9?g_st=ipc",
    "https://maps.app.goo.gl/1bWfr7zMXSvwF11s8?g_st=ipc",
    "https://maps.app.goo.gl/kr9CHWTNtC32pSLK8?g_st=ipc",
    "https://maps.app.goo.gl/mUKZjW3zBVn4iZqz6?g_st=ipc",
    "https://maps.app.goo.gl/rzt2zBBVP5451rKK9?g_st=ipc",  # 這個跟上面重複，看你要不要刪掉
    "https://maps.app.goo.gl/WZH1vy2K6bQ5sJT96?g_st=ipc",
    "https://maps.app.goo.gl/JYitYJrFXjcqaHqK9?g_st=ipc",
    "https://maps.app.goo.gl/3A9xUnWKdGxdWTuE8?g_st=ipc",
    "https://maps.app.goo.gl/xTfMLFTujsqKXUK38?g_st=ipc",
    "https://maps.app.goo.gl/ZHV5Mnxq8ZFNjGyVA?g_st=ipc",
    "https://maps.app.goo.gl/zLgdtzsj7Rp1ZfSZA?g_st=ipc",
    "https://maps.app.goo.gl/SeAXF5MXAcVgbf8o7?g_st=ipc",
    "https://maps.app.goo.gl/oFA4hURpZ2CNpZgV7?g_st=ipc",
    "https://maps.app.goo.gl/YhSXEkBhw9M7tEPL6?g_st=ipc",
    
]

@measure_time
def recommend_restaurants(tk, uid):
    """
    使用者在「景點推薦」底下選『餐廳』時，
    從 RESTAURANT_URLS 隨機抽 1 個網址推播出去。
    """
    lang = _get_lang(uid)

    # 標題文字
    head = (
        "以下是為您隨機推薦的一間淡水餐廳：" if lang == "zh"
        else "Here is a randomly selected restaurant in Tamsui:"
    )

    # 從清單中隨機抽 1 個網址
    url = random.choice(RESTAURANT_URLS)

    # 組成兩則訊息：說明 + 連結
    msgs = [
        TextSendMessage(text=head),
        TextSendMessage(text=url),
    ]

    safe_reply(tk, msgs, uid)



@measure_time
def recommend_general_places(tk, uid):
    """
    一般景點推薦：加入性別轉換後的模型呼叫
    """

  
    # 確保 lang 在 try 區塊外初始化，以便在 except 區塊中使用
    lang = _get_lang(uid)
    
    try:
        # 5) 產生 Flex Message
        
        # 1. 定義 6 個固定網址
        urls = [
            "https://newtaipei.travel/zh-tw/attractions/detail/109658"
        ]

        # 2. 設定標題
        head = "以下是為您推薦的淡水景點：" if lang == "zh" else "Here are the recommended attractions in Tamsui:"

        # 3. 產生訊息列表
        msgs = [TextSendMessage(text=head)] + [
            TextSendMessage(text=url) for url in urls
        ]

        # 4. 傳送訊息
        safe_reply(tk, msgs, uid)
        
    except Exception as e:
        # 保留錯誤處理，防止服務崩潰
        print("❌ recommend_general_places error:", e)
        # 假設 _t 和 TextSendMessage 已經被導入
        safe_reply(tk, TextSendMessage(text=_t('data_fetch_failed', lang)), uid)

@measure_time
def send_attraction_menu(tk, uid):
    """
    使用者選「景點」時，先列出可選的景點，請他輸入名稱
    """
    lang = _get_lang(uid)

    if lang == "zh":
        lines = [
            "以下是可選擇的淡水景點：",
            "",
            "1. 淡水老街",
            "2. 漁人碼頭",
            "3. 金色水岸",
            "4. 滬尾砲台",
            "5. 紅毛城",
            "6. 沙崙海灘",
            "",
            "請輸入想去景點的代號或名稱，例如：1或是淡水老街"
        ]
    else:
        lines = [
            "Here are the attractions in Tamsui:",
            "",
            "1. Tamsui Old Street",
            "2. Fisherman’s Wharf",
            "3. Golden Riverside",
            "4. Huwei Fort",
            "5. Fort San Domingo",
            "6. Shalun Beach",
            "",
            "Please type the number or the name of the attraction, e.g. 1 or Tamsui Old Street"
        ]

    msg = "\n".join(lines)
    safe_reply(tk, TextSendMessage(text=msg), uid)

    # 下一句文字就當成「選擇哪個景點」
    shared.user_stage[uid] = "choose_attraction"
    
@measure_time
def handle_attraction_choice(uid, text, replyTK):
    """
    當 stage == 'choose_attraction' 時，使用者輸入的文字會到這裡
    支援：
      - 中文全名：淡水老街
      - 英文全名：Tamsui Old Street
      - 代號：1～6
    """
    lang = _get_lang(uid)
    name_raw = text.strip()

    # ---- 0. 先試著把輸入當「代號」處理（1～6） ----
    # 允許使用者輸入「1」、「1.」、「1、」這種形式
    code = "".join(ch for ch in name_raw if ch.isdigit())
    if code in PLACE_CODES:
        zh_name = PLACE_CODES[code]                # 先取得中文名稱
        url = PLACE_URLS.get(zh_name)

        if url:
            # 顯示給使用者看的名稱：中文介面用中文，英文介面轉英文
            display_name = to_en(zh_name) if lang == "en" else zh_name

            if lang == "zh":
                reply_text = f"這是「{display_name}」的連結：\n{url}"
            else:
                reply_text = f"Here is the link for {display_name}:\n{url}"

            safe_reply(replyTK, TextSendMessage(text=reply_text), uid)
            # ❗ 不改 stage，維持在 choose_attraction，讓他可以繼續輸入下一個
            return
        # 如果照理說不會發生，還是讓它往下走用舊邏輯

    # ---- 1. 英文輸入轉成中文 key ----
    lower = name_raw.lower()
    EN2ZH = {
        "tamsui old street":   "淡水老街",
        "fisherman’s wharf":   "漁人碼頭",
        "fisherman's wharf":   "漁人碼頭",
        "golden riverside":    "金色水岸",
        "huwei fort":          "滬尾砲台",
        "fort san domingo":    "紅毛城",
        "shalun beach":        "沙崙海灘",
    }

    if lang == "en":
        key = EN2ZH.get(lower, name_raw)   # 找不到就用原字串當 key
    else:
        key = name_raw                     # 中文直接用原本輸入

    # ---- 2. 用「中文 key」去查 PLACE_URLS ----
    url = PLACE_URLS.get(key)

    if url:
        if lang == "zh":
            reply_text = f"這是「{key}」的連結：\n{url}"
        else:
            # 英文時顯示原本輸入的英文名稱比較自然
            reply_text = f"Here is the link for {name_raw}:\n{url}"

        safe_reply(replyTK, TextSendMessage(text=reply_text), uid)
        # ✅ 不把 stage 改回 ready，這樣可以連續查多個景點
        # shared.user_stage[uid] = "ready"
    else:
        if lang == "zh":
            reply_text = "抱歉，我找不到這個景點，請確認名稱再輸入一次（例如：淡水老街 或 1）"
        else:
            reply_text = "Sorry, I can't find this attraction. Please type the exact name or its number (e.g. 1)."

        safe_reply(replyTK, TextSendMessage(text=reply_text), uid)
        # 保持在 choose_attraction，等使用者再輸入一次



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
        raw_gender  = shared.user_gender.get(uid, "")
        gender_code = FlexMessage.classify_gender(raw_gender)   # 0/1/2
        age         = shared.user_age.get(uid, 30)

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
        #header = f"📊 {crowd_msg}"
        title  = to_en('永續觀光') if lang == 'en' else '永續觀光'
        body   = f"{title}：{rec}\n{web}\n{maplink}"

        safe_reply(tk, [
            TextSendMessage(text=body),
            
        ],uid)

    except Exception as e:
        print("❌ recommend_sustainable_places error:", e)
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
        raw_gender  = shared.user_gender.get(uid, "")
        gender_code = FlexMessage.classify_gender(raw_gender)   # 0/1/2
        age         = shared.user_age.get(uid, 30)

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
        #header = f"📊 {crowd_msg}"
        title  = to_en('永續觀光') if lang == 'en' else '永續觀光'
        body   = f"{title}：{rec}\n{web}\n{maplink}"

        safe_reply(tk, [
            TextSendMessage(text=body),
            
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
    url = "https://pda5284.gov.taipei/MQS/stoplocation.jsp?slid=3845"

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
    shared.user_collecting[uid] = True


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

    ask_student_buttons(uid, replyTK)

# 在 app.py 中新增，放在 handle_language、handle_gender_buttons 之後，handle_message_event 之前
@measure_time
def ask_student_buttons(uid, replyTK):
    """
    第二步：問使用者「你是否為學生？」（是 / 否 按鈕）
    """
    lang = _get_lang(uid)

    question = "你是否為學生？" if lang == "zh" else "Are you a student?"

    # 按鈕的文字與回傳文字一樣（中文：是/否；英文：Yes/No）
    yes_label = "是" if lang == "zh" else "Yes"
    no_label  = "否" if lang == "zh" else "No"

    actions = [
        MessageAction(label=yes_label, text=yes_label),
        MessageAction(label=no_label,  text=no_label),
    ]

    tpl = ButtonsTemplate(text=question, actions=actions)
    safe_reply(
        replyTK,
        TemplateSendMessage(alt_text=question, template=tpl),
        uid
    )
    # 更新階段
    shared.user_stage[uid] = "ask_student"


@measure_time
def handle_student(uid, text, replyTK):
    """
    處理「是否為學生？」的回答（stage='ask_student'）
    回覆必須是：中文：是/否；英文：Yes/No
    """
    lang = _get_lang(uid)
    low  = text.lower()

    is_student = None
    if lang == "zh":
        if text == "是":
            is_student = True
        elif text == "否":
            is_student = False
    else:
        if low == "yes":
            is_student = True
        elif low == "no":
            is_student = False

    if is_student is None:
        # 使用者沒有按按鈕，而是亂打字
        msg = "請點選「是」或「否」" if lang == "zh" else 'Please tap "Yes" or "No".'
        safe_reply(replyTK, TextSendMessage(text=msg), uid)
        return

    # ✅ 把是否為學生記起來（你要在 shared.py 補上一行：user_student = {}）
    shared.user_student[uid] = is_student

    # 下一步：跟原本一樣，進到「選擇性別」按鈕
    handle_gender_buttons(uid, lang, replyTK)


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
    if shared.user_collecting.get(uid) == True:
        shared.user_collecting[uid] = False   # 清除 flag
        shared.user_stage[uid] = "ready"      # 返回主選單
        reply_text = (
            "感謝您的填寫！您的資料已成功更新。請使用其他功能 😊"
            if _get_lang(uid) == "zh"
            else "Thank you! Your information has been updated. Please continue using other features!"
        )
        safe_reply(replyTK, TextSendMessage(text=reply_text), uid)
        return
        
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

def _update_location_memory(uid, lat, lon):
    """Update a user's in-memory location regardless of current stage."""
    try:
        lat = float(lat); lon = float(lon)
        shared.user_location[uid] = (lat, lon)
        print(f"[loc] updated for {uid}: ({lat}, {lon})")
    except Exception as e:
        print(f"[loc] update failed for {uid}: {e}")

@measure_time
def handle_days(uid, text, replyTK):
    zh_days = ["兩天一夜", "三天兩夜", "四天三夜", "五天四夜"]
    eng2zh  = {to_en(d): d for d in zh_days}
    lang    = _get_lang(uid)
    choice  = eng2zh.get(text, text)

    if choice not in zh_days:
        safe_reply(replyTK, TextSendMessage(text=_t("invalid_days", lang)),uid)
        return

    shared.user_trip_days[uid]   = choice
    shared.user_preparing[uid]   = True
    shared.user_plan_ready[uid]  = False
    shared.user_stage[uid]       = 'ready'

    threading.Thread(
        target=_background_planning,
        args=(choice, replyTK, uid),
        daemon=True
    ).start()

    safe_reply(replyTK, TextSendMessage(text=_t("please_wait", lang)),uid)


def handle_free_command(uid, text, replyTK):
    """
    Ready 階段的自由指令處理：
    包含「收集資料」「景點人潮」「行程規劃」
    「景點推薦」「永續觀光」「附近搜尋」
    「關鍵字搜尋」「租車」「更新位置」等指令。
    """
    from linebot.models import (
        TextSendMessage, TemplateSendMessage, ConfirmTemplate,
        QuickReply, QuickReplyButton, MessageAction, StickerSendMessage
    )
    import threading
    if shared.user_stage.get(uid) != 'ready':
        shared.user_stage[uid] = 'ready'

    low = text.lower()

    # 使用者目前狀態
    preparing = shared.user_preparing.get(uid, False)
    plan_ready = shared.user_plan_ready.get(uid, False)
    days      = shared.user_trip_days.get(uid)  # e.g. "三天兩夜"
    days_label = to_en(days) if _get_lang(uid) == 'en' and days else days

    # 指令集合
    recollect_keys   = {"收集資料", "data collection", "collect data"}
    crowd_keys       = {"景點人潮", "景點人潮(crowd analyzer)", "crowd analyzer", "crowd analysis", "crowd info"}
    plan_keys        = {"行程規劃", "行程規劃(itinerary planning)", "itinerary planning", "plan itinerary"}
    recommend_keys   = {"景點推薦", "景點推薦(attraction recommendation)", "attraction recommendation", "recommend spot"}
    sustainable_keys = {"餐廳", "餐廳(restaurant)", "restaurant", "2-1"}
    general_keys     = {"景點", "景點(attraction)", "attraction", "2-2"}
    nearby_keys      = {"附近搜尋", "附近搜尋(nearby search)", "nearby search"}
    rental_keys      = {"租車", "租車(car rental)", "car rental information", "car rental", "大眾運輸", "public transport", "大眾運輸(public transport)"}
    update_loc_keys  = {"更新位置", "update location", "set location"}   # ← 新增
        # ---- 關鍵字對應（中英都吃）----
    keyword_map = {
        "附近餐廳": "restaurants nearby",
        "停車場":   "parking",
        "服務":     "service",
        "住宿":     "accommodation",
    }

    best_tamsui_keys = {
        "淡水個人推薦",
        "淡水推薦景點",
        "tamsui recommendation",
        "tamsui best spot"
    }
    
    # 使用者輸入是否是我們的關鍵字（中文 or 英文）
    is_keyword = text in keyword_map or low in set(keyword_map.values())


    # 1) 重新收集資料
    if low in recollect_keys:
        handle_ask_language(uid, replyTK)
        return

    # 2) 景點人潮
    if low in crowd_keys:
        send_crowd_analysis(replyTK, uid)
        return

    # 3) 行程規劃
    if low in plan_keys:
        if preparing:
            safe_reply(replyTK, TextSendMessage(text=_t("prep_in_progress", _get_lang(uid))), uid)
        elif plan_ready:
            safe_reply(replyTK, FlexMessage.ask_route_option(), uid)
            # 推送詳細說明
            if _get_lang(uid) == 'en':
                desc1    = f"Using machine learning based on relevance, we found the best {days_label} itinerary for you"
                sys_label = _t("system_route", 'en')
                desc_sys  = (
                    f"【{sys_label}】\n"
                    "1. Show full route (red line).\n"
                    "2. Show segment by segment (blue line).\n"
                    "3. Clear system route."
                )
                usr_label = _t("user_route", 'en')
                desc_usr  = (
                    f"【{usr_label}】\n"
                    "1. Tap \"Add to route\" to include in list.\n"
                    "2. Show all at once (green line).\n"
                    "3. Show segment by segment (orange line).\n"
                    "4. Clear user route."
                )
            else:
                desc1    = f"以機器學習依據相關性，找尋過往數據最適合您的{days_label}行程"
                sys_label = _t("system_route", 'zh')
                desc_sys  = (
                    f"【{sys_label}】依照人潮較少規劃\n"
                    "1. 整段顯示完整路線（紅線）。\n"
                    "2. 分段逐段顯示（藍線）。\n"
                    "3. 清除系統路線。"
                )
                usr_label = _t("user_route", 'zh')
                desc_usr  = (
                    f"【{usr_label}】\n"
                    "1. 點「加入路線」加入清單。\n"
                    "2. 一次性顯示（綠線）。\n"
                    "3. 分段逐段顯示（橘線）。\n"
                    "4. 清除使用者路線。"
                )
            safe_push(uid, [
                TextSendMessage(text=desc1),
                TextSendMessage(text=desc_sys),
                TextSendMessage(text=desc_usr),
            ])
        else:
            if days:
                shared.user_preparing[uid]  = True
                shared.user_plan_ready[uid] = False
                threading.Thread(
                    target=_background_planning,
                    args=(days, replyTK, uid),
                    daemon=True
                ).start()
                safe_reply(replyTK, TextSendMessage(text=_t("please_wait", _get_lang(uid))), uid)
            else:
                safe_reply(replyTK, TextSendMessage(text=_t("collect_info", _get_lang(uid))), uid)
        return

    # 4) 景點推薦 → 詢問永續 vs 一般
    if low in recommend_keys:
        yes_lbl     = _t("restaurant", _get_lang(uid))
        no_lbl      = _t("attraction",  _get_lang(uid))
        payload_yes = "餐廳" if _get_lang(uid) == 'zh' else "restaurant"
        payload_no  = "景點" if _get_lang(uid) == 'zh' else "attraction"
        tpl = ConfirmTemplate(
            text=_t("ask_sustainable", _get_lang(uid)),
            actions=[
                MessageAction(label=yes_lbl, text=payload_yes),
                MessageAction(label=no_lbl,  text=payload_no),
            ]
        )
        safe_reply(replyTK, TemplateSendMessage(alt_text=_t("ask_sustainable", _get_lang(uid)), template=tpl), uid)
        return

    # 5) 永續 or 一般景點推薦
    if low in sustainable_keys:
        # 餐廳照舊：用 XGBoost 那個永續推薦（你也可以之後改成餐廳選單）
        recommend_restaurants(replyTK, uid)
        return

    if low in general_keys:
        # 景點：改成出景點選單，讓使用者輸入名稱
        send_attraction_menu(replyTK, uid)
        return



    # 6) 附近搜尋
    if low in nearby_keys:
        safe_reply(replyTK, FlexMessage.ask_keyword(), uid)
        return

    # 6.5) 手動要求更新位置（彈出 LINE 位置分享 UI） ← 新增
    if low in update_loc_keys:
        safe_reply(replyTK, FlexMessage.ask_location(), uid)
        return

    # 7) 關鍵字搜尋
    if is_keyword:
        lang = _get_lang(uid)

        # 中文與英文都對應到同一個 type
        type_map = {
            "附近餐廳":          "food",
            "restaurants nearby": "food",

            "停車場":            "parking",
            "parking":           "parking",

            "住宿":              "stay",
            "accommodation":     "stay",

            "服務":              "service",
            "service":           "service",
        }

        key = text if text in type_map else low
        t   = type_map.get(key)

        if t:
            base = "https://phen-line-547744493031.asia-east1.run.app"

            # 🌏 根據語言切換中文／英文版網址
            if lang == "zh":
                # 原本的中文：/map_guide?type=...
                url  = f"{base}/map_guide?type={t}"
                head = "以下是為您查詢到的地圖連結："
            else:
                # 新增的英文版：/map_guide_en?type=...
                # 會對應到你提供的這四個網址：
                # service:       .../map_guide_en?type=service
                # accommodation: .../map_guide_en?type=stay
                # parking:       .../map_guide_en?type=parking
                # food:          .../map_guide_en?type=food
                url  = f"{base}/map_guide_en?type={t}"
                head = "Here is the map link for your selection:"

            safe_reply(
                replyTK,
                [
                    TextSendMessage(text=head),
                    TextSendMessage(text=url),
                ],
                uid
            )
        else:
            # 理論上不會進來，只是保險
            safe_reply(replyTK, TextSendMessage(text=_t("data_fetch_failed", lang)), uid)

        return

    # 7.5) 淡水 XGBoost 個人化推薦
    if low in best_tamsui_keys:
        recommend_best_tamsui_spot(replyTK, uid)
        return
        

    # 8) 租車資訊
    if low in rental_keys:
        send_rental_car(replyTK, uid)
        return

    # 9) 其他不處理
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

def _get_effective_location_for_user(uid):
    """
    優先從記憶體 shared.user_location 取得 (lat, lon)。
    若不存在，再 fallback 到 get_location.get_location(LOCATION_FILE)（保留原有行為）。
    回傳 (lat, lon)（float），或丟出 Exception（不能決定位置時）。
    """
    # 1) 優先用記憶體中的位置（handle_location 存入的）
    loc = shared.user_location.get(uid)
    if loc and isinstance(loc, (tuple, list)) and len(loc) == 2:
        try:
            return float(loc[0]), float(loc[1])
        except Exception:
            pass

    # 2) fallback：從 LOCATION_FILE 讀（原程式之行為）
    try:
        lat, lon = get_location.get_location(LOCATION_FILE)
        return float(lat), float(lon)
    except Exception as e:
        raise RuntimeError(f"Cannot determine location for uid={uid}") from e


def handle_postback_event(ev, uid, lang, replyTK):
    """
    統一處理所有 Postback 事件（替換版）。
    - 支援性別按鈕
    - 支援天數按鈕（background planning）
    - 支援 系統路線 / 使用者路線：**改為優先使用 shared.user_location 再 fallback 到 LOCATION_FILE**
    - 其餘 postback 仍會被記錄
    """
    try:
        data = ev.get("postback", {}).get("data", "")
    except Exception:
        data = ev.get("postback", {}).get("params", {}).get("data", "")
    print(f"[postback] uid={uid}, data={data}, shared_loc={shared.user_location.get(uid)}")

    # 性別按鈕
    if data in ("男", "女", "其他"):
        handle_gender(uid, data, replyTK)
        return

    # 天數按鈕（兩天一夜、三天兩夜、四天三夜、五天四夜）
    if data in ("兩天一夜", "三天兩夜", "四天三夜", "五天四夜"):
        try:
            shared.user_trip_days[uid] = data
            shared.user_preparing[uid] = True
            shared.user_plan_ready[uid] = False
            shared.user_stage[uid] = 'ready'

            # 回覆並啟動背景規劃（注意：這裡把 replyTK 傳給使用者前端，background 使用 None）
            safe_reply(replyTK, TextSendMessage(text=_t("please_wait", lang)), uid)
            threading.Thread(
                target=_background_planning,
                args=(data, None, uid),
                daemon=True
            ).start()
        except Exception as e:
            print(f"Error handling days postback for uid={uid}: {e}")
            safe_reply(replyTK, TextSendMessage(text=_t("data_fetch_failed", lang)), uid)
        return

    # 系統路線 / 使用者路線（優先用 shared.user_location）
    sys_zh, usr_zh = "系統路線", "使用者路線"
    sys_en, usr_en = to_en(sys_zh), to_en(usr_zh)

    # 處理系統路線
    if data in (sys_zh, sys_en):
        try:
            lat, lon = _get_effective_location_for_user(uid)
            uid_qs = urllib.parse.quote_plus(uid)
            # 用固定小數位格式化，避免 None 或長浮點數
            url = f"https://system-plan.eeddyytaddy.workers.dev/?uid={uid_qs}&lat={lat:.6f}&lng={lon:.6f}"
            print(f"[postback->system-plan] uid={uid}, url={url}")
            safe_reply(replyTK, TextSendMessage(text=url), uid)
            shared.user_stage[uid] = 'ready'
        except Exception as e:
            print(f"Error getting location for system route uid={uid}: {e}")
            safe_reply(replyTK, TextSendMessage(text=_t("cannot_get_location", lang)), uid)
        return

    # 處理使用者路線
    if data in (usr_zh, usr_en):
        try:
            lat, lon = _get_effective_location_for_user(uid)
            uid_qs = urllib.parse.quote_plus(uid)
            url = f"https://user-plan.eeddyytaddy.workers.dev/?uid={uid_qs}&lat={lat:.6f}&lng={lon:.6f}"
            print(f"[postback->user-plan] uid={uid}, url={url}")
            safe_reply(replyTK, TextSendMessage(text=url), uid)
            shared.user_stage[uid] = 'ready'
        except Exception as e:
            print(f"Error getting location for user route uid={uid}: {e}")
            safe_reply(replyTK, TextSendMessage(text=_t("cannot_get_location", lang)), uid)
        return

    # 其他 Postback 一律記錄但不處理
    print(f"Unhandled postback data for uid={uid}: {data}")
    return


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

        # —— Location in ANY stage: update memory and acknowledge ——
        if msgType == "location":
            # 若正好在引導流程的 got_location，就沿用原本的 handle_location（會給天數 QuickReply）
            if shared.user_stage.get(uid, 'ask_language') == 'got_location':
                handle_location(uid, msg, replyTK)
            else:
                # 其他階段：單純更新位置並回覆提示
                _update_location_memory(uid, msg.get("latitude"), msg.get("longitude"))
                safe_reply(replyTK, TextSendMessage(text=_t("position_saved", _get_lang(uid))), uid)
            return

        # —— 0) 重啟資料收集流程 ——
        if msgType == "text" and text.startswith("收集資料"):
            handle_ask_language(uid, replyTK)
            return

               # —— 1) 自由指令 ——
        crowd_keys  = {"景點人潮", "crowd analyzer", "3", "景點人潮(crowd analyzer)"}
        plan_keys   = {"行程規劃", "plan itinerary", "6", "行程規劃(itinerary planning)"}
        rec_keys    = {"景點推薦", "attraction recommendation", "2", "景點推薦(attraction recommendation)"}
        sust_keys   = {"餐廳", "restaurant", "2-1"}
        gen_keys    = {"景點", "attraction", "2-2"}
        nearby_keys = {"附近搜尋", "nearby search", "4", "附近搜尋(nearby search)"}
        rental_keys = {"大眾運輸", "public transport", "5", "大眾運輸(public transport)"}
        keyword_map = {"附近餐廳": "restaurants nearby", "停車場": "parking", "服務": "service", "住宿": "accommodation"}
        is_keyword  = text in keyword_map or low in set(keyword_map.values())

        # 先抓目前階段
        stage = shared.user_stage.get(uid, 'ask_language')
        number_keys = {"1", "2", "3", "4", "5", "6"}

        if msgType == "text":
            # ✅ 如果正在「選景點」階段，且輸入的是 1～6，
            #    不要當作主選單指令處理，讓下面的 stage flow
            #    去執行 handle_attraction_choice()
            if stage == "choose_attraction" and text in number_keys:
                pass
            else:
                # 行程規劃：若缺資料則引導補齊（原本程式不變）
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
                            safe_reply(
                                replyTK,
                                TextSendMessage(text=_t("ask_days", current_lang),
                                                quick_reply=QuickReply(items=qr_items)),
                                uid
                            )
                        return

                # 其他自由指令／關鍵字
                if (low in crowd_keys or low in rec_keys or low in sust_keys or 
                    low in gen_keys or low in nearby_keys or low in rental_keys or is_keyword):
                    handle_free_command(uid, text, replyTK)
                    return


        # —— 2) 階段流程 ——
        stage = shared.user_stage.get(uid, 'ask_language')
        print(f"[Stage flow] type={msgType}, text={text}, stage={stage}")
        # —— 處理是否為學生 ——  
        if stage == "ask_student" and msgType == "text":
            handle_student(uid, text, replyTK)
            return


        # 第一步：選擇語言
        if stage == 'ask_language' and msgType == "text":
            if low in ("中文", "zh", "english", "en"):
                handle_language(uid, text, replyTK)
            else:
                safe_reply(replyTK, TextSendMessage(text=_t("invalid_language", _get_lang(uid))), uid)
            return

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

        # Ready 階段：自由指令
        if stage == 'ready' and msgType == "text":
            handle_free_command(uid, text, replyTK)
            return

        # 使用者正在選景點（從景點選單來的）
        if stage == "choose_attraction" and msgType == "text":
            handle_attraction_choice(uid, text, replyTK)
            return

        # 圖片／貼圖
        if msgType == "image":
            safe_reply(replyTK, TextSendMessage(text=_t("data_fetch_failed", _get_lang(uid))), uid)
            return
        if msgType == "sticker":
            safe_reply(replyTK, StickerSendMessage(package_id=msg.get("packageId"),
                                                   sticker_id=msg.get("stickerId")), uid)
            return

        # 其他不處理
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
    print("🚀 Flask server start …")
    os.environ.setdefault('APP_ENV', 'loadtest')
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)), debug=True)

# ---------------- END OF app.py ------------------------------------
