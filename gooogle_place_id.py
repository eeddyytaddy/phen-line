# add_place_id.py

import csv
import googlemaps
import time
import os

from config import BEACON_INPUT_CSV, BEACON_OUTPUT_CSV

# 設定你的 Google API 金鑰（請確保環境變數 GOOGLE_MAPS_API_KEY 已正確設定）
API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
gmaps = googlemaps.Client(key=API_KEY)

def add_place_id_to_csv(infile, outfile, limit=6000):
    # 讀取時假設檔案編碼為 utf-8-sig，根據實際檔案調整編碼
    with open(infile, mode='r', newline='', encoding='utf-8-sig') as fin, \
         open(outfile, mode='w', newline='', encoding='utf-8-sig') as fout:

        reader = csv.DictReader(fin)
        if reader.fieldnames is None:
            print("CSV 沒有標題列")
            return

        # 若原始欄位中沒有 place_id 則新增
        if "place_id" not in reader.fieldnames:
            fieldnames = reader.fieldnames + ["place_id"]
        else:
            fieldnames = reader.fieldnames

        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()

        count = 0
        for row in reader:
            if count >= limit:
                break

            place_name = row.get("設置點", "")
            lat = row.get("緯度", "")
            lng = row.get("經度", "")

            place_id = ""

            # 先以地點名稱查詢
            try:
                response = gmaps.find_place(
                    input=place_name, 
                    input_type="textquery", 
                    fields=["place_id"]
                )
            except Exception as e:
                print(f"API 查詢錯誤，地點名稱: {place_name}，錯誤: {e}")
                response = {}

            if response.get("status") == "OK" and response.get("candidates"):
                place_id = response["candidates"][0].get("place_id", "")
            else:
                # 若以名稱查詢無結果，嘗試逆向地理編碼
                try:
                    reverse_geocode_result = gmaps.reverse_geocode((lat, lng))
                    if reverse_geocode_result:
                        place_id = reverse_geocode_result[0].get("place_id", "")
                except Exception as e:
                    print(f"逆向地理編碼錯誤，座標({lat}, {lng})，錯誤: {e}")
                    place_id = ""

            row["place_id"] = place_id
            writer.writerow(row)
            count += 1

            # 延遲以避免 API 請求過快
            time.sleep(0.1)

    print(f"已將前 {count} 筆查詢到的 place_id 寫入新檔案: {outfile}")

if __name__ == "__main__":
    add_place_id_to_csv(BEACON_INPUT_CSV, BEACON_OUTPUT_CSV, limit=6000)
