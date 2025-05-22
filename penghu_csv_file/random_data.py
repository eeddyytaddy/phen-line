import pandas as pd
import random
import numpy as np

# 設定生成資料的筆數
num_records = 3000  # 可以根據需要修改這個數值

# 定義初始資料
data = {
    'no': list(range(0, num_records)),
    'Time': pd.date_range(start='2022-02-01 00:00:00', periods=num_records, freq='1H').strftime('%m/%d/%Y %I:%M:%S %p').tolist(),
    'POI': [random.choice(['0150deb7d0,0089', '0150deb7d0,0102', '0150deb7d0,0112', '0150deb7d0,0384', '0150deb7d0,0401', '0150deb7d0,0157', '0150deb7d0,0024']) for _ in range(num_records)],
    'UserID/MemID': [f'{random.randint(1000000000000000000000000000000000000000000, 9999999999999999999999999999999999999999999):x}' for _ in range(num_records)],
    '設置點': [random.choice(['離島出走 Isle Travel', '澎湖七美莫咖啡 More Coffee', '鄭家莊｜澎湖七美民宿', '年年有鰆', 'O2 Lab 海漂實驗室', '撒野旅店 Say Yeah Inn', '南寮風車有機農場｜風島物產']) for _ in range(num_records)],
    '緯度': np.random.uniform(23.5, 23.7, num_records).round(4),
    '經度': np.random.uniform(119.5, 119.6, num_records).round(4),
    'BPL UID': [random.randint(220000, 230000) for _ in range(num_records)],
    'age': [random.randint(18, 80) for _ in range(num_records)],
    'gender': [random.randint(0, 1) for _ in range(num_records)],
    'weather': [random.choice(['晴', '風雨', '多雲']) for _ in range(num_records)],
    'temperature': np.random.uniform(15, 33, num_records).round(1),
    'tidal': [random.randint(1, 2) for _ in range(num_records)]
}

# 創建 DataFrame
df = pd.DataFrame(data)

# 保存為 UTF-8 編碼的 CSV 檔案
csv_file_path = "C:/Users/wkao_/Desktop/NCLab/penghu project/penghu_csv_file/generated_data_updated1.csv"
df.to_csv(csv_file_path, index=False, encoding='utf-8-sig')

csv_file_path
