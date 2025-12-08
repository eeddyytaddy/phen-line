# zh2en.py
"""
Centralized Chinese-to-English mappings and multilingual UI text
for the Penghu LINE Bot.
"""

# ------------------------------------------------------------------
#  一、單句中文 → 英文對照（主要用於按鈕 label / QuickReply 文字）
# ------------------------------------------------------------------
ZH2EN: dict[str, str] = {
    # === Route type ===
    "系統路線": "System Route",
    "使用者路線": "User Route",

    # === Trip duration labels ===
    "兩天一夜": "2-day 1-night",
    "三天兩夜": "3-day 2-night",
    "四天三夜": "4-day 3-night",
    "五天四夜": "5-day 4-night",

    # === Main-menu commands ===
    "行程規劃": "Plan Itinerary",
    "景點推薦": "Recommend Spot",
    "永續觀光": "Sustainable Tourism",
    "一般景點推薦": "General Recommendation",
    "景點人潮": "Crowd Analysis",
    "附近搜尋": "Nearby Search",
    "大眾運輸": "public transport",
    "景點": "attraction",
    "餐廳": "restaurant",

    # === Nearby-search keywords ===
    "風景區": "Scenic Spots",
    "餐廳":   "Restaurants",
    "停車場": "Parking",
    "住宿":   "Accommodation",

    # === Gender ===
    "男": "Male",
    "女": "Female",
    "其他": "Other",

    # === Yes / No ===
    "餐廳": "restaurant",
    "景點": "attraction",

    # === Questionnaire / help ===
    "填寫問卷": "Fill Questionnaire",
    "需要幫助": "Need Help",
    "好":       "OK",

    # === Price level (Google place) ===
    "免費":       "Free",
    "低價位":     "Cheap",
    "中等價位":   "Moderate",
    "較高價位":   "Expensive",
    "高價位":     "Very Expensive",
    "無價格資訊": "No Price Info",
    "約":         "approx.",

    # === Misc actions ===
    "查看地圖":   "View Map",

    # === Planning status (短語映射) ===
    "規劃完成": "Planning Completed",
    "規劃失敗": "Planning Failed",
}

def to_en(chinese_label: str) -> str:
    """
    Convert a Chinese label to its English counterpart.
    If not found, returns the original text unchanged.
    """
    return ZH2EN.get(chinese_label, chinese_label)


# ------------------------------------------------------------------
#  二、介面多語文字 (TEXTS) —— 依 key 取中/英文句子
# ------------------------------------------------------------------
TEXTS: dict[str, dict[str, object]] = {
    # ----------------------------  繁體中文  ----------------------------
    "zh": {
        # 基本互動
        "ask_language":        "請選擇語言：『中文』或『英文』\nPlease select language: 'Chinese' or 'English'",
        "invalid_language":    "請輸入正確指令",
        "ask_age":             "你是否是學生?",
        "ask_gender":          "請選擇你的性別",
        "ask_days":            "請選擇旅行天數",
        "ask_student_bottons": "你是否是學生?",

        # 位置與行程
        "position_saved":      "位置已儲存，請選擇預計旅行天數：",
        "storage_failed":      "位置儲存失敗",
        "please_wait":         "👍 我正在準備你的行程，請先使用其他功能",
        "prep_in_progress":    "行程還在準備中，請先使用其他功能",
        "collect_info":        "⚠️ 請先完成資料收集",
        "cannot_get_location": "無法取得您的位置，請重新傳送位置資訊",
        "ask_location":        "謝謝您的填寫!您的資料已傳送至規劃旅程。請使用其他功能，祝您旅途愉快!",

        # 驗證
        "enter_valid_age":     "請輸入正確年紀",
        "enter_number":        "請輸入數字",

        # 行程規劃
        "ask_route_option":    "請選擇您要的路線",
        "system_route":        "系統路線",
        "user_route":          "使用者路線",

        # 規劃結果通知（已加入）
        "planning_completed":  "✅ 行程規劃完成！",
        "planning_failed":     "❌ 行程規劃失敗，請稍後再試。",

        # 景點推薦
        "restaurant": "餐廳",
        "attraction": "景點",

        # 數據/網路
        "data_fetch_failed":   "資料取得失敗，請稍後再試。",

        # 問卷
        "reply_questionnaire": "請點擊以下連結填寫問卷：",

        # 推薦 / 人潮
        "system_recommend":     "系統推薦：",
        "crowd_top5":           "目前最擁擠前五景點",
        "sustainable_recommend":"永續觀光推薦：",
        "ask_sustainable":      "請點選推薦項目",

        # 連結提示
        "ask_keyword":         "請選擇搜尋的關鍵字",
        "send_location":       "傳送位置",
        "crowd_analysis_link": "請點選以下網址查看人潮分析",
        "visit_spots_url":     "以下網址推薦附近景點：",
        "visit_cars_url":      "以下網址推薦公車動態",

        # 價格顯示前綴
        "price_label":         "價格：",
        "view_map": ' 查看地圖',
        "no_price_info": '沒價錢資訊',

        # 價格對應表（Google price_level 0-4）
        "price_map": {
            0: "免費",
            1: "低價位",
            2: "中等價位",
            3: "較高價位",
            4: "高價位",
        },

        # Nearby keywords
        "風景區": "風景區",
        "餐廳":   "餐廳",
        "停車場": "停車場",
        "住宿":   "住宿",
    },

    # ----------------------------  English  ----------------------------
    "en": {
        # Basics
        "ask_language":        "請選擇語言：『中文』或『英文』\nPlease select language: 'Chinese' or 'English'",
        "invalid_language":    "Please enter the correct command",
        "ask_age":             "Are you a student?",
        "ask_gender":          "Please select your gender",
        "ask_days":            "Please choose trip duration",
        "ask_location":        "Thanks for your information!Your information have been sent to Travel planning. Please use other options.Wish you have a pleasant journey!",
        "send_location":       "Send Location",
        "ask_student_bottons": "Are you a student?",

        # 規劃結果通知（已加入）
        "planning_completed":  "✅ Your itinerary is ready.",
        "planning_failed":     "❌ Itinerary planning failed. Please try again later.",

        # 景點推薦
        "restaurant": "restaurant",
        "attraction": "attraction",

        # Location / trip
        "position_saved":      "Location saved, please select trip duration:",
        "storage_failed":      "Failed to save location",
        "please_wait":         "👍 I am preparing your trip. Please wait and use other functions first.",
        "prep_in_progress":    "Your itinerary is still being prepared. Please wait and use other functions first.",
        "collect_info":        "⚠️ Please complete data collection first",
        "cannot_get_location": "Cannot get your location, please resend it",

        # Validation
        "enter_valid_age":     "Please enter a valid age",
        "enter_number":        "Please enter a number",

        # Data / network
        "data_fetch_failed":   "Failed to fetch data, please try again later.",

        # Questionnaire
        "reply_questionnaire": "Please click the link below to fill out the questionnaire:",

        # Recommendation / crowd
        "system_recommend":     "System recommends: ",
        "crowd_top5":           "Current top 5 crowded spots",
        "sustainable_recommend":"Sustainable tourism recommendation: ",
        "ask_sustainable":      "Please choose the recommend item",
        "ask_keyword":          "Please select the search keyword",
        "crowd_analysis_link":  "Click the link below for crowd analysis",
        "visit_spots_url":      "URL for nearby attractions:",
        "visit_cars_url":       "URL for public transport:",

        # Trip routing
        "ask_route_option":     "Please select your desired route",
        "system_route":         "System Route",
        "user_route":           "User Route",

        # 價格顯示前綴
        "price_label":          "Price: ",
        "view_map": ' view map',
        "no_price_info": 'no price info',

        # 價格對應表（Google price_level 0-4）
        "price_map": {
            0: "Free",
            1: "Cheap",
            2: "Moderate",
            3: "Expensive",
            4: "Very Expensive",
        },

        # Nearby keywords
        "風景區": "Scenic Spots",
        "餐廳":   "Restaurants",
        "停車場": "Parking",
        "住宿":   "Accommodation",
    }
}
