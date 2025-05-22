import csv
import json
import requests
from config import PLAN_CSV, WORKER_URL,D1_BINDING
from timer import measure_time
import sqlite3
# 定義欄位轉換對應字典
FIELD_MAPPING = {
    "no": "no",
    "Time": "time",
    "time": "time",
    "POI": "poi",
    "poi": "poi",
    "UserID/MemID": "user_id",
    "設置點": "place",
    "緯度": "latitude",
    "經度": "longitude",
    "BPL UID": "bplu_id",
    "age": "age",
    "gender": "gender",
    "天氣": "weather",
    "place_id": "place_id",
    "crowd": "crowd",
    "crowd_rank": "crowd_rank"
}

def csv_to_json(file_path):
    """
    讀取 CSV 檔案，將每一列轉換成字典後返回 JSON 資料，
    並補齊所有 expected_keys，預防 undefined。
    """
    records = []
    expected_keys = {
        "no", "time", "poi", "user_id", "place", "latitude", "longitude",
        "bplu_id", "age", "gender", "weather", "place_id", "crowd", "crowd_rank"
    }
    # 指定哪些欄位預設為 "0"
    zero_defaults = {"crowd", "crowd_rank"}
    try:
        with open(file_path, mode='r', encoding='utf-8-sig', newline='') as fin:
            reader = csv.DictReader(fin)
            for row in reader:
                # 略過完全空的列
                if not any(row.values()):
                    continue

                # 1) 欄位名稱對應
                new_row = {}
                for key, value in row.items():
                    new_key = FIELD_MAPPING.get(key, key)
                    new_row[new_key] = value

                # 2) 補齊所有 expected_keys
                for k in expected_keys:
                    if k not in new_row or new_row[k] is None:
                        # crowd / crowd_rank 用 "0"，其餘用空字串
                        new_row[k] = "0" if k in zero_defaults else ""

                records.append(new_row)
    except Exception as e:
        print(f"讀取 CSV 過程中發生錯誤: {e}")
    return records


def send_to_worker(data):
    """
    使用 HTTP POST 請求將 JSON 資料傳送到 Cloudflare Worker。
    資料以 {"records": [...]} 格式傳送，並設定 Content-Type 為 UTF-8。
    """
    headers = {
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {"records": data}
    try:
        response = requests.post(WORKER_URL, json=payload, headers=headers)
        print(f"HTTP 狀態碼: {response.status_code}")
        return response
    except Exception as e:
        print("發送請求失敗:", e)
        return None

def csv_up():
    # 1. 讀 CSV 並轉成 JSON（list of dict）
    data = csv_to_json(PLAN_CSV)

    # 2. **寫入本地 SQLite**  
    save_to_sqlite(data, db_path=D1_BINDING)

    # 3. 印出轉換後的 JSON 以供檢查
    print("轉換後的 JSON 資料:")
    print(json.dumps(data, ensure_ascii=False, indent=2))

    # 4. 呼叫 Worker
    response = send_to_worker(data)
    if response is not None:
        print("Worker 回傳結果:")
        print(response.text)
    else:
        print("無法取得 Worker 回傳結果。")


@measure_time
def save_to_sqlite(records, db_path='local.db'):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # 假設你已經用下面 SQL 建好表：
    # CREATE TABLE plan (
    #   no TEXT, time TEXT, poi TEXT, user_id TEXT,
    #   place TEXT, latitude REAL, longitude REAL,
    #   bplu_id TEXT, age INTEGER, gender INTEGER,
    #   weather TEXT, place_id TEXT,
    #   crowd INTEGER, crowd_rank INTEGER
    # );
    insert_sql = """
      INSERT INTO plan
      (no, time, poi, user_id, place, latitude, longitude,
       bplu_id, age, gender, weather, place_id, crowd, crowd_rank)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    for rec in records:
        cur.execute(insert_sql, (
           rec["no"], rec["time"], rec["poi"], rec["user_id"],
           rec["place"], float(rec["latitude"] or 0), float(rec["longitude"] or 0),
           rec["bplu_id"], int(rec["age"] or 0), int(rec["gender"] or 0),
           rec["weather"], rec["place_id"],
           int(rec["crowd"] or 0), int(rec["crowd_rank"] or 0)
        ))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    csv_up()
