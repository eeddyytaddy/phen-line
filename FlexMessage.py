import os
import json
import csv
import urllib.parse
from flask import request
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    BubbleContainer, BoxComponent, TextComponent, ButtonComponent,
    SeparatorComponent, ImageComponent, QuickReply, QuickReplyButton,
    CarouselContainer, IconComponent, FlexSendMessage, TextSendMessage,
    PostbackAction, LocationAction, URIAction, MessageAction
)
from linebot.models import BubbleContainer, BoxComponent, ImageComponent, TextComponent, ButtonComponent, URIAction, FlexSendMessage
from zh2en import TEXTS as I18N, to_en, ZH2EN
from shared import user_language  # 每位使用者的語系設定 dict

# LINE API
ACCESS_TOKEN   = os.getenv("LINE_ACCESS_TOKEN",   "your_line_access_token_here")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "your_line_channel_secret_here")
line_bot_api   = LineBotApi(ACCESS_TOKEN)
handler        = WebhookHandler(CHANNEL_SECRET)
GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
def _get_lang(uid: str) -> str:
    return user_language.get(uid, 'zh')

def _t(key: str, lang: str) -> str:
    return I18N.get(lang, I18N['zh']).get(key, key)

def sanitize_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return "https://" + url.lstrip("/")

def text_stars(rating: float) -> str:
    """純文字的星等顯示"""
    full = int(rating)
    half = 1 if (rating - full) >= 0.5 else 0
    empty = 5 - full - half
    return "★" * full + ("½" if half else "") + "☆" * empty

# === ask_keyword ===
def ask_keyword():
    body = request.get_data(as_text=True)
    ev   = json.loads(body)['events'][0]
    uid  = ev['source']['userId']
    lang = _get_lang(uid)

    prompt   = _t('ask_keyword', lang)
    hero_raw = "zh-tw.skyticket.com/guide/wp-content/uploads/2020/12/shutterstock_1086233933.jpg"
    hero_url = sanitize_url(hero_raw)

    # 中英對應的按鈕文字與回傳
    def make_kw_button(chinese_key):
        label = _t(chinese_key, lang)
        text_payload = to_en(chinese_key) if lang == 'en' else chinese_key
        return ButtonComponent(
            style='secondary', height='sm',
            action=MessageAction(label=label, text=text_payload)
        )

    bubble = BubbleContainer(
        direction='ltr',
        hero=ImageComponent(
            url=hero_url,
            preview_image_url=hero_url,
            size='full', aspect_ratio='20:15', aspect_mode='cover'
        ),
        body=BoxComponent(
            layout='horizontal',
            contents=[TextComponent(text=prompt, size='xl', align='center', wrap=True)]
        ),
        footer=BoxComponent(
            layout='vertical', spacing='xs',
            contents=[
                # 第一行
                BoxComponent(
                    layout='horizontal', spacing='xs',
                    contents=[
                        # 風景區
                        BoxComponent(
                            layout='vertical', spacing='xs',
                            contents=[
                                ImageComponent(
                                    url=sanitize_url("i.imgur.com/0H0JmYX.png"),
                                    preview_image_url=sanitize_url("i.imgur.com/0H0JmYX.png"),
                                    aspect_ratio="1:1", aspect_mode="cover", size="md"
                                ),
                                make_kw_button('風景區')
                            ]
                        ),
                        # 餐廳
                        BoxComponent(
                            layout='vertical', spacing='xs',
                            contents=[
                                ImageComponent(
                                    url=sanitize_url("thumb.silhouette-ac.com/t/d8/d8a7e9674d55ca5fe9173b02cc4fb7dd_w.jpeg"),
                                    preview_image_url=sanitize_url("thumb.silhouette-ac.com/t/d8/d8a7e9674d55ca5fe9173b02cc4fb7dd_w.jpeg"),
                                    aspect_ratio="1:1", aspect_mode="cover", size="md"
                                ),
                                make_kw_button('餐廳')
                            ]
                        ),
                    ]
                ),
                # 第二行
                BoxComponent(
                    layout='horizontal', spacing='xs',
                    contents=[
                        # 停車場
                        BoxComponent(
                            layout='vertical', spacing='xs',
                            contents=[
                                ImageComponent(
                                    url=sanitize_url("th.bing.com/th/id/OIP.VgsoPsjpE4Pb9BRWjZ5tFwAAAA?pid=ImgDet&rs=1"),
                                    preview_image_url=sanitize_url("th.bing.com/th/id/OIP.VgsoPsjpE4Pb9BRWjZ5tFwAAAA?pid=ImgDet&rs=1"),
                                    aspect_ratio="1:1", aspect_mode="cover", size="md"
                                ),
                                make_kw_button('停車場')
                            ]
                        ),
                        # 住宿
                        BoxComponent(
                            layout='vertical', spacing='xs',
                            contents=[
                                ImageComponent(
                                    url=sanitize_url("png.pngtree.com/png-vector/20190623/ourlarge/pngtree-hotel-icon-png-image_1511479.jpg"),
                                    preview_image_url=sanitize_url("png.pngtree.com/png-vector/20190623/ourlarge/pngtree-hotel-icon-png-image_1511479.jpg"),
                                    aspect_ratio="1:1", aspect_mode="cover", size="md"
                                ),
                                make_kw_button('住宿')
                            ]
                        ),
                    ]
                )
            ]
        )
    )
    return FlexSendMessage(alt_text=prompt, contents=bubble)


def Rating_Component(rating):
    rating = float(rating)
    rating_str = str(rating)
    integer_part, decimal_part = rating_str.split('.')
    integer_part = int(integer_part)
    decimal_part = int(decimal_part)
    component = []
    for _ in range(integer_part):
        icon_component = IconComponent(
            size='sm',
            url="https://scdn.line-apps.com/n/channel_devcenter/img/fx/review_gold_star_28.png"
        )
        component.append(icon_component)
    if integer_part == 0:
        integer_part = 1
    if integer_part < 5:
        if decimal_part < 4:
            icon_component = IconComponent(
                size='sm',
                url="https://scdn.line-apps.com/n/channel_devcenter/img/fx/review_gray_star_28.png"
            )
            component.append(icon_component)
        elif 3 < decimal_part < 8:
            icon_component = IconComponent(
                size='sm',
                url="https://i.imgur.com/8eAZJ80.png"
            )
            component.append(icon_component)
        else:
            icon_component = IconComponent(
                size='sm',
                url="https://scdn.line-apps.com/n/channel_devcenter/img/fx/review_gold_star_28.png"
            )
            component.append(icon_component)
        integer_part = integer_part + 1
    if integer_part < 5:
        for _ in range(5 - integer_part):
            icon_component = IconComponent(
                size='sm',
                url="https://scdn.line-apps.com/n/channel_devcenter/img/fx/review_gray_star_28.png"
            )
            component.append(icon_component)
    text_component = TextComponent(
        text=rating_str,
        size='sm',
        color="#999999",
        margin="md",
        flex=0
    )
    component.append(text_component)
    return component

# === recommend helper ===
def recommend(
    name,
    rating,
    img_url,
    location,
    place_id,
    google_price_level=None,
    average_price=None,
    uid=None               # <── 重新加入
):
    """
    產生推薦店家資訊的 Flex Bubble
    - 支援 zh / en 兩語系（依 uid）
    - 價格等級以 google_price_level 為準；沒有就整行隱藏
    """
    # ---------- 語系 ----------
    lang = _get_lang(uid)            # zh / en

    # ---------- 評分星星 ----------
    component = Rating_Component(rating)   # 你既有的函式

    # ---------- 價格對照 ----------
    price_mapping_zh = {0: "免費", 1: "低價位", 2: "中等價位", 3: "較高價位", 4: "高價位"}
    price_mapping_en = {0: "Free", 1: "Budget", 2: "Moderate", 3: "Pricey", 4: "Expensive"}
    price_mapping    = price_mapping_en if lang == "en" else price_mapping_zh

    # ---------- 正規化 price_level ----------
    def _normalize(val):
        if val in (None, "", "null", "None", "-", "N/A"):
            return None
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return None

    lvl = _normalize(google_price_level)
    price_text = price_mapping.get(lvl) if lvl is not None else None

    # ---------- average_price ----------
    avg_text = ""
    if average_price not in (None, "", "null", "None", "-", "N/A"):
        try:
            avg = float(average_price)
            currency = "NT$" if lang == "zh" else "NT$"   # 這裡兩語系皆顯示 NT$
            approx   = "約" if lang == "zh" else "≈"
            avg_text = f" ({approx} {currency}{int(avg)})"
        except (ValueError, TypeError):
            pass

    show_price = price_text is not None or avg_text != ""
    price_info = (price_text or _t("no_price_info", lang)) + avg_text if show_price else None

    # ---------- 解析 location ----------
    lat = lng = 0
    if isinstance(location, dict):
        lat, lng = location.get("lat", 0), location.get("lng", 0)
    else:
        try:
            loc_dict = json.loads(location)
            lat, lng = loc_dict.get("lat", 0), loc_dict.get("lng", 0)
        except Exception:
            pass

    # ---------- Google Maps URL ----------
    name_encoded = urllib.parse.quote(name, safe="")
    if place_id and place_id.strip().lower() not in ("no information", "none", ""):
        maps_url = (
            f"https://www.google.com/maps/search/?api=1"
            f"&query={name_encoded}&query_place_id={place_id}"
        )
    else:
        maps_url = (
            f"https://www.google.com/maps/search/?api=1"
            f"&query={name_encoded}+{lat},{lng}"
        )

    # ---------- 建立 body ----------
    body_contents = [
        TextComponent(text=name, size="xl", color="#000000", wrap=True),
        BoxComponent(layout="baseline", margin="md", contents=component),
    ]

    if show_price:
        price_label = "價格等級: " if lang == "zh" else "Price level: "
        body_contents.append(
            TextComponent(
                text=f"{price_label}{price_info}",
                size="md",
                color="#000000",
                wrap=True,
            )
        )

    # ---------- Bubble ----------
    bubble = BubbleContainer(
        direction="ltr",
        hero=ImageComponent(
            url=img_url,
            align="center",
            size="full",
            aspect_ratio="20:15",
            aspect_mode="cover",
        ),
        body=BoxComponent(layout="vertical", contents=body_contents),
        footer=BoxComponent(
            layout="vertical",
            spacing="xs",
            contents=[
                ButtonComponent(
                    style="secondary",
                    color="#FFEE99",
                    height="sm",
                    action=URIAction(
                        label=_t("view_map", lang) if "view_map" in I18N.get(lang, {}) else "查看地圖",
                        uri=maps_url,
                    ),
                )
            ],
        ),
    )

    return bubble





def Carousel_contents(file_path, uid):
    rows = list(csv.reader(open(file_path, encoding="utf-8-sig")))[1:11]
    bubbles = []
    for row in rows:
        name, _, rating, img, loc, pid, *rest = row
        bubble = recommend(
            name=name,
            rating=rating,
            img_url=img,
            location=loc,
            place_id=pid,
            google_price_level=rest[0] if rest else None,
            average_price=rest[1] if len(rest) > 1 else None,
            uid=uid
        )
        bubbles.append(bubble)
    return bubbles

def Carousel(contents, uid=None):
    alt = _t('shop_info', _get_lang(uid))
    return FlexSendMessage(alt_text=alt, contents=CarouselContainer(contents=contents))


# === ask_location ===
def ask_location():
    body = request.get_data(as_text=True)
    ev   = json.loads(body)['events'][0]
    uid  = ev['source']['userId']
    lang = _get_lang(uid)

    prompt     = _t('ask_location', lang)
    send_label = _t('send_location', lang)

    bubble = BubbleContainer(
        direction="ltr",
        body=BoxComponent(
            layout="horizontal",
            contents=[TextComponent(text=prompt, size="xl", align="center", wrap=True)]
        )
    )
    msg = FlexSendMessage(alt_text=prompt, contents=bubble)
    msg.quick_reply = QuickReply(
        items=[QuickReplyButton(action=LocationAction(label=send_label, text=send_label))]
    )
    return msg


# === ask_route_option ===
def ask_route_option():
    body = request.get_data(as_text=True)
    ev   = json.loads(body)['events'][0]
    uid  = ev['source']['userId']
    lang = _get_lang(uid)

    prompt  = _t('ask_route_option', lang)
    sys_txt = _t('system_route', lang)
    usr_txt = _t('user_route', lang)
    # 按鈕標籤
    label_sys = to_en(sys_txt) if lang == 'en' else sys_txt
    label_usr = to_en(usr_txt) if lang == 'en' else usr_txt

    bubble = BubbleContainer(
        direction="ltr",
        body=BoxComponent(
            layout="vertical",
            contents=[
                TextComponent(
                    text=prompt,
                    size="md",
                    align="center",
                    wrap=True
                )
            ]
        ),
        footer=BoxComponent(
            layout="vertical", spacing="xs",
            contents=[
                ButtonComponent(
                    style="primary",
                    action=PostbackAction(
                        label=label_sys,
                        text=label_sys,
                        data=label_sys
                    )
                ),
                ButtonComponent(
                    style="primary",
                    action=PostbackAction(
                        label=label_usr,
                        text=label_usr,
                        data=label_usr
                    )
                )
            ]
        )
    )
    return FlexSendMessage(alt_text=prompt, contents=bubble)


def classify_gender(gender: str) -> int:
    return {'男': 1, '女': 0, '其他': -1}.get(gender, -1)
