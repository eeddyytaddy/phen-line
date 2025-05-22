import csv
import json
import mysql.connector
from datetime import datetime, date
from collections import defaultdict
import unicodedata
from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE

def normalize_str(s):
    """去除前後空白並作 Unicode 正規化"""
    return unicodedata.normalize('NFKC', s.strip())

# 連接 MySQL
conn = mysql.connector.connect(
    host=MYSQL_HOST,
    port=MYSQL_PORT,
    user=MYSQL_USER,
    password=MYSQL_PASSWORD,
    database=MYSQL_DATABASE,
    charset='utf8'
)
cursor = conn.cursor()

# 建立資料表（若尚未存在）
create_table_query = """
CREATE TABLE IF NOT EXISTS crowd_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    place_id VARCHAR(255) NOT NULL,
    place_name VARCHAR(255),
    historical_crowd TEXT,  -- 以 JSON 形式儲存 24 小時人潮統計
    avg_intensity FLOAT,
    lat FLOAT,
    lng FLOAT,
    record_date DATE
)
"""
cursor.execute(create_table_query)
conn.commit()

# Step 1: 讀取 crowd_with_place_id__filtered2.csv，建立以 place_name 為 key 的對照
place_mapping = {}
with open(r"C:\Users\user\Desktop\Penghu\PH_project_v1-main\PH_project_v1-main\penghu_csv_file\crowd_with_place_id__filtered2.csv", newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        key = normalize_str(row.get('place_name', ''))
        place_id = normalize_str(row.get('place_id', ''))
        # 若 CSV 中有 lat、lng，則直接取用
        try:
            lat_val = float(row.get('lat', '').strip() or 0.0)
            lng_val = float(row.get('lng', '').strip() or 0.0)
        except:
            lat_val, lng_val = 0.0, 0.0
        if key:
            place_mapping[key] = {
                'place_id': place_id,
                'lat': lat_val,
                'lng': lng_val
            }

# Step 2: 讀取 Beacon20220907-crowd.csv，統計每個地點 24 小時人潮
# 我們將用一個字典存群組計數，並記錄顯示名稱及 fallback 的 user_id（若有）
crowds_dict = {}        # key: group_key, value: [24 小時計數]
display_name_dict = {}  # key: group_key, value: 顯示名稱 (取自設置點優先)
fallback_userid = {}    # key: group_key, value: 該筆資料的 UserID/MemID（若設置點存在但對應不到 mapping）
coords_dict = {}        # key: group_key, value: (lat, lng) 來自 Beacon CSV

with open(r"C:\Users\user\Desktop\Penghu\PH_project_v1-main\PH_project_v1-main\penghu_csv_file\Beacon20220907-crowd.csv", newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        beacon_place = normalize_str(row.get('設置點', ''))
        user_id = normalize_str(row.get('UserID/MemID', ''))
        # 使用設置點為主要分組鍵，若設置點為空則使用 UserID/MemID
        if beacon_place:
            group_key = beacon_place
            display_name = beacon_place
            # 儲存 fallback user_id (即使 beacon_place 存在，也可能對 mapping 失敗)
            if user_id:
                fallback_userid[group_key] = user_id
        else:
            group_key = user_id
            display_name = user_id

        # 初始化群組
        if group_key not in crowds_dict:
            crowds_dict[group_key] = [0]*24
            display_name_dict[group_key] = display_name

        time_str = row.get('Time', '').strip()
        if not time_str:
            continue
        try:
            dt = datetime.strptime(time_str, "%m/%d/%Y %I:%M:%S %p")
            hour_of_day = dt.hour
        except Exception:
            hour_of_day = 0
        crowds_dict[group_key][hour_of_day] += 1

        # 取得 Beacon CSV 中的經緯度（以最新一筆為準）
        try:
            lat_val = float(row.get('緯度', '').strip() or 0.0)
            lng_val = float(row.get('經度', '').strip() or 0.0)
            coords_dict[group_key] = (lat_val, lng_val)
        except:
            pass

# Step 3: 將彙整好的 24 小時人潮資料寫入 MySQL
record_date = date.today()

for group_key, hour_counts in crowds_dict.items():
    # 先嘗試以 group_key (通常為設置點) 在 mapping 中找對應
    mapping = place_mapping.get(group_key, None)
    # 如果找不到，且有 fallback user_id，則嘗試以 fallback user_id 在 mapping 中找
    if mapping is None and group_key in fallback_userid:
        fallback_key = fallback_userid[group_key]
        mapping = place_mapping.get(fallback_key, None)
    
    # 取得最終的 place_id 與座標
    if mapping:
        place_id = mapping['place_id']
        lat_val = mapping['lat']
        lng_val = mapping['lng']
        # 如果 mapping 中的座標均為 0，且 Beacon CSV 提供了座標，則採用 Beacon 資料
        if (lat_val == 0.0 and lng_val == 0.0) and (group_key in coords_dict):
            lat_val, lng_val = coords_dict[group_key]
    else:
        place_id = 'unknown'
        if group_key in coords_dict:
            lat_val, lng_val = coords_dict[group_key]
        else:
            lat_val, lng_val = 0.0, 0.0

    # 使用 display_name_dict[group_key] 當作 place_name（通常為 Beacon CSV 中的設置點）
    place_name_final = display_name_dict.get(group_key, group_key)
    avg_intensity = sum(hour_counts) / 24.0
    historical_crowd_json = json.dumps(hour_counts)
    
    insert_query = """
    INSERT INTO crowd_data (place_id, place_name, historical_crowd, avg_intensity, lat, lng, record_date)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    cursor.execute(insert_query, (
        place_id,
        place_name_final,
        historical_crowd_json,
        avg_intensity,
        lat_val,
        lng_val,
        record_date
    ))

conn.commit()
cursor.close()
conn.close()
print("Beacon20220907-crowd.csv 資料處理完成，已寫入 MySQL。")
