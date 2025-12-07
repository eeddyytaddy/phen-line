import xgboost as xgb
import joblib
import pandas as pd
import numpy as np
from config import TAMSUI_MODEL_FILE, TAMSUI_ENCODER_FILE, OUT_PUT

# ============================
# 1. 載入模型與編碼器
# ============================

try:
    model = xgb.XGBRegressor()
    model.load_model(TAMSUI_MODEL_FILE)
    encoders = joblib.load(TAMSUI_ENCODER_FILE)
    print("模型與編碼器載入成功！")
except Exception as e:
    print(f"載入失敗，請先執行訓練程式 (Tamsui_model_train.py)。錯誤: {e}")
    exit()

# ============================
# 2. 定義預測函數
# ============================
def predict_preference(identity_input, gender_input):
    """
    輸入身分與性別，回傳該使用者對所有景點的預測評分
    """
    
    # 取得所有景點名稱
    all_attractions = encoders['Attraction'].classes_
    
    # 準備輸入資料
    # 我們需要為每一個景點建立一筆輸入數據
    input_data = []
    
    try:
        id_code = encoders['Identity'].transform([identity_input])[0]
        gender_code = encoders['Gender'].transform([gender_input])[0]
    except ValueError as e:
        return f"輸入錯誤: {e}。請確認輸入值是否符合訓練資料 (如 Student, Male)。"

    for attr in all_attractions:
        attr_code = encoders['Attraction'].transform([attr])[0]
        input_data.append([id_code, gender_code, attr_code])
    
    # 轉換為 DataFrame (feature names 必須與訓練時一致)
    X_pred = pd.DataFrame(input_data, columns=['Identity_Code', 'Gender_Code', 'Attraction_Code'])
    
    # 進行預測
    predicted_scores = model.predict(X_pred)
    
    # 整理結果
    results = pd.DataFrame({
        '景點 (Attraction)': all_attractions,
        '預測評分 (Predicted Rating)': predicted_scores
    })
    
    # 按照分數排序
    results = results.sort_values(by='預測評分 (Predicted Rating)', ascending=False)
    return results

# ============================
# 3. 互動式測試
# ============================
if __name__ == "__main__":
    identity_input = input("請輸入身份 (如 Student, Worker): ") 
    gender_input = input("請輸入性別 (如 Male, Female): ") 

    results = predict_preference(identity_input, gender_input)

    if isinstance(results, str):
        print(results)
    else:
        print("\n預測結果：")
        print(results)

        # === 將預測結果輸出到 CSV ===
        results.to_csv(OUT_PUT, index=False, encoding="utf-8-sig")


        print(f"\n✔ 預測結果已成功輸出到 CSV：{OUT_PUT}")

