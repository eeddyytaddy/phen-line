# Googlemap_function.py

import googlemaps
from time import sleep
import urllib.parse
import pandas as pd
import csv
import os

from config import RECOMMEND_CSV, HOTEL_DATA_CSV

# 透過環境變數獲取 Google Maps API 金鑰
api_key = os.getenv("GOOGLE_MAPS_API_KEY")
gmaps = googlemaps.Client(key=api_key)

def googlemap_search_nearby(lat, lng, keyword):
    """
    搜尋指定經緯度 2 公里內的指定類別地點（例如餐廳、景點），並將結果存入 CSV。
    """
    loc = {'lat': lat, 'lng': lng}
    rad = 2000
    results = gmaps.places_nearby(keyword=keyword, radius=rad, location=loc)['results']
    
    placeID_list = [place['place_id'] for place in results]
    hotel_info = [gmaps.place(place_id=pid, language="zh-TW")['result'] for pid in placeID_list]
    sleep(0.1)
        
    search_list = []
    maxwidth = 800
    for h in hotel_info:
        name = h['name'][:40] if len(h['name']) >= 50 else h['name']
        
        # Google Maps 圖片 URL
        try:
            photoreference = h['photos'][0]['photo_reference']
            img_url = (
                f'https://maps.googleapis.com/maps/api/place/photo'
                f'?maxwidth={maxwidth}&photoreference={photoreference}&key={api_key}'
            )
            img_url = urllib.parse.quote(img_url, safe=':/?&=')
        except Exception:
            img_url = (
                "https://th.bing.com/th/id/R.409832a9886d51eb28e38d9f5a312cb9"
                "?rik=RoSWoLpVeJgp5A&riu=http%3a%2f%2fwww.allsense.com.tw"
                "%2fshopt%2fimages%2fs1%2fnotImg_.jpg"
            )

        # Google Maps 地圖 URL
        place_id = h["place_id"]
        map_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"

        dic = {
            'name': name,
            'price_level': h.get('price_level', "N/A"),
            'rating': h.get('rating', "0"),
            'img_url': img_url,
            'place_id': place_id,
            'location': h['geometry']['location'],
            'map_url': map_url
        }
        search_list.append(dic)

    # 寫入 CSV
    with open(RECOMMEND_CSV, 'w+', newline='', encoding='utf-8-sig') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['name', 'price_level', 'rating', 'img_url', 'location', 'place_id', 'map_url'])
        search_list = sorted(search_list, key=lambda row: float(row["rating"]), reverse=True)
        for h in search_list:
            writer.writerow([
                h['name'],
                h['price_level'],
                h['rating'],
                h['img_url'],
                h['location'],
                h['place_id'],
                h['map_url']
            ])
    print("寫入檔案完成:", RECOMMEND_CSV)

    return search_list, len(results)

def googlemap_search_hotel(lat, lng):
    """
    搜尋指定經緯度 2 公里內的住宿地點，包含圖片 URL，並將結果存入 CSV。
    """
    loc = {'lat': lat, 'lng': lng}
    rad = 2000
    results = gmaps.places_nearby(keyword="住宿", radius=rad, location=loc)['results']
    
    placeID_list = [place['place_id'] for place in results]
    hotel_info = [gmaps.place(place_id=pid, language="zh-TW")['result'] for pid in placeID_list]
    sleep(0.3)
    
    maxwidth = 800
    name_list, latitude_list, longitude_list, url_list = [], [], [], []
    for h in hotel_info:
        name = h['name'][:40] if len(h['name']) >= 50 else h['name']
        try:
            photoreference = h['photos'][0]['photo_reference']
            img_url = (
                f'https://maps.googleapis.com/maps/api/place/photo'
                f'?maxwidth={maxwidth}&photoreference={photoreference}&key={api_key}'
            )
            img_url = urllib.parse.quote(img_url, safe=':/?&=')
        except Exception:
            img_url = "no information"
        
        name_list.append(name)
        latitude_list.append(h['geometry']['location']['lat'])
        longitude_list.append(h['geometry']['location']['lng'])
        url_list.append(img_url)

    # 寫入 CSV
    with open(HOTEL_DATA_CSV, 'w+', newline='', encoding='utf-8-sig') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["hotel_name", "latitude", "longitude", "url"])
        writer.writerows(zip(name_list, latitude_list, longitude_list, url_list))
    print("寫入檔案完成:", HOTEL_DATA_CSV)

    return len(results), name_list
