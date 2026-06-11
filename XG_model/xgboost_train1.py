import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import mean_squared_error, r2_score
import joblib
import numpy as np

from config import CSV_FILE, TAMSUI_MODEL_FILE, TAMSUI_ENCODER_FILE
# ============================
# 1. 設定與讀取資料
# ============================

print(f"正在讀取資料: {CSV_FILE}...")
df = pd.read_csv(CSV_FILE)

# ============================
# 2. 資料前處理 (Data Preprocessing)
# ============================
# 定義景點欄位
attractions = [
    'Fort San Domingo', 'Tamsui Old Street', 'Tamshui Gold Seashore',
    'Hobe Fort', "Fisherman's Wharf", 'Shalun Beach'
]

# 檢查欄位是否存在
missing_cols = [col for col in attractions if col not in df.columns]
if missing_cols:
    raise ValueError(f"缺少欄位: {missing_cols}")

# --- 關鍵步驟：將寬表格轉為長表格 (Melt) ---
# 轉換前: [User, Gender, Score_A, Score_B]
# 轉換後: [User, Gender, Attraction_Name] -> Rating
melted_df = df.melt(
    id_vars=['Identity', 'Gender'], # 保留的身分特徵
    value_vars=attractions,         # 要轉置的景點欄位
    var_name='Attraction',          # 新的景點名稱欄位
    value_name='Rating'             # 新的評分欄位
)

print(f"資料轉換完成，樣本數: {len(melted_df)}")

# ============================
# 3. 特徵編碼 (Label Encoding)
# ============================
# 初始化編碼器
le_identity = LabelEncoder()
le_gender = LabelEncoder()
le_attraction = LabelEncoder()

# 執行編碼
melted_df['Identity_Code'] = le_identity.fit_transform(melted_df['Identity'])
melted_df['Gender_Code'] = le_gender.fit_transform(melted_df['Gender'])
melted_df['Attraction_Code'] = le_attraction.fit_transform(melted_df['Attraction'])

# 準備特徵 (X) 與目標 (y)
X = melted_df[['Identity_Code', 'Gender_Code', 'Attraction_Code']]
y = melted_df['Rating']

# ============================
# 4. 模型訓練 (Training)
# ============================
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

print("開始訓練 XGBoost 模型...")
MODEL = xgb.XGBRegressor(
    n_estimators=100,
    learning_rate=0.1,
    max_depth=5,
    random_state=42,
    objective='reg:squarederror'
)

MODEL.fit(X_train, y_train)

# ============================
# 5. 評估與儲存 (Evaluation & Saving)
# ============================
predictions = MODEL.predict(X_test)
mse = mean_squared_error(y_test, predictions)
r2 = r2_score(y_test, predictions)

print("="*30)
print(f"模型評估結果:")
print(f"MSE (均方誤差): {mse:.4f}")
print(f"R2 Score (準確度): {r2:.4f}") # 因為您的數據是規律生成的，這裡應該會接近 1.0
print("="*30)

# 儲存模型
MODEL.save_model(TAMSUI_MODEL_FILE)
print(f"模型已儲存至: {TAMSUI_MODEL_FILE}")

# 儲存編碼器 (預測時需要用來解碼)
encoders = {
    'Identity': le_identity,
    'Gender': le_gender,
    'Attraction': le_attraction
}
joblib.dump(encoders, TAMSUI_ENCODER_FILE)

print(f"編碼器已儲存至: {TAMSUI_ENCODER_FILE}")

