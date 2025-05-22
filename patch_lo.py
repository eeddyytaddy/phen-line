# route_filter.py

import pandas as pd
from config import PLAN_CSV, BEACON_OUTPUT_CSV

def get_planned_route(plan_csv):
    """
    讀取機器學習產生的規劃路徑檔案，
    假設檔案中有 'place_id' 欄位，依照出現順序取出各景點。
    """
    df = pd.read_csv(plan_csv, encoding='utf-8-sig')
    planned_route = df['place_id'].unique().tolist()
    return planned_route

def filter_route(crowd_csv, planned_route):
    """
    讀取人潮 CSV 檔案，統計各景點出現次數，
    並建立 place_id 與中文名稱（設置點）的對應關係，
    再從原始路徑中移除人潮最高前五的景點，
    同時印出原始路徑、熱門景點與調整後的路徑（包含中文名稱）。
    """
    df = pd.read_csv(crowd_csv, encoding='utf-8-sig')
    crowd_counts = df['place_id'].value_counts()
    name_mapping = df.groupby('place_id')['設置點'].first()

    print("原始規劃路線:")
    for pid in planned_route:
        print(f"{pid} - {name_mapping.get(pid, '無中文名稱')}")

    top5_places = crowd_counts.nlargest(5).index.tolist()
    print("\n人潮最高的前五個景點 (需避開):")
    for pid in top5_places:
        print(f"{pid} - {name_mapping.get(pid, '無中文名稱')}")

    filtered_route = [pid for pid in planned_route if pid not in top5_places]
    print("\n調整後的規劃路線 (避開前五大人潮景點):")
    for pid in filtered_route:
        print(f"{pid} - {name_mapping.get(pid, '無中文名稱')}")

    return filtered_route

if __name__ == "__main__":
    # 從 config 取得路徑
    plan_csv  = PLAN_CSV
    crowd_csv = BEACON_OUTPUT_CSV

    # 取得並過濾路線
    planned_route  = get_planned_route(plan_csv)
    filtered_route = filter_route(crowd_csv, planned_route)
