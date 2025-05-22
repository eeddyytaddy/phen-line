from config import PLAN_2DAY, PLAN
import os
import csv

def filter(file, userID):
    # 打開 CSV 檔案進行讀取
    with open(file, mode='r', newline='', encoding='utf-8-sig') as rfile:
        reader = csv.DictReader(rfile)
        # 設置篩選條件
        filter_condition = {'UserID/MemID': userID}
        # 定義欲輸出欄位（移除多餘逗號，並不包含 "place_id"）
        fieldnames = ['no', 'Time', 'POI', 'UserID/MemID', '設置點', '緯度', '經度', 'BPL UID', 'age', 'gender', '天氣']
        
        with open(PLAN, mode='w', newline='', encoding='utf-8-sig') as wfile:
            writer = csv.DictWriter(wfile, fieldnames=fieldnames)
            writer.writeheader()
            # 逐行讀取並檢查是否符合條件
            for row in reader:
                # 移除不在 fieldnames 裡的鍵，例如 "place_id"
                keys_to_remove = [key for key in row if key not in fieldnames]
                for key in keys_to_remove:
                    del row[key]
                # 檢查 row 是否符合篩選條件
                if all(row.get(key) == value for key, value in filter_condition.items()):
                    writer.writerow(row)

# 執行篩選
filter(PLAN_2DAY, 'U16f92b0df914c40495c60e84bf79adba')
