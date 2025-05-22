# XGBOOST_predicted.py

import xgboost as xgb
import Now_weather
from random import randrange
import numpy as np
from sklearn.preprocessing import LabelEncoder, OneHotEncoder
import pandas as pd
from xgboost import XGBClassifier

from config import (
    PENGHU_ORIGINAL_CSV,
    GENERATED_DATA_CSV,
    SUSTAINABLE_ATTR_CSV,
    NON_SUSTAINABLE_ATTR_CSV,
    SUSTAINABLE_NON_ATTR_CSV,
    NON_SUSTAINABLE_NON_ATTR_CSV,
    XGB_MODEL1_PATH,
    XGB_MODEL2_PATH,
    PHTEST_MODEL_PATH,
    SUSTAINABLE_MODEL_PATH,
    NON_SUSTAINABLE_MODEL_PATH,
    SUSTAINABLE_NON_MODEL_PATH,
    NON_SUSTAINABLE_NON_MODEL_PATH,
)

# ---------------------------
# 輔助函式
# ---------------------------
def safe_onehot_transform(onehotencoder, input_data):
    try:
        final = onehotencoder.transform(input_data)
    except ValueError as e:
        print("❌ OneHotEncoder.transform() 出錯:", e, flush=True)
        print("🚨 輸入數據:", input_data, flush=True)
        raise e
    return final

def safe_label_transform(labelencoder, arr, default_value=0):
    try:
        arr_labelencode = labelencoder.transform(arr)
    except ValueError as e:
        print("❌ LabelEncoder.transform() 出錯:", e, flush=True)
        print("🚨 輸入 weather array:", arr, flush=True)
        print("⚠️ 使用預設值:", default_value, flush=True)
        arr_labelencode = np.array([default_value])
    return arr_labelencode

def check_and_set_defaults(**kwargs):
    defaults = {'gender': -1, 'age': 30, 'tidal': 0, 'temperature': 20}
    for key, default in defaults.items():
        if key in kwargs and kwargs[key] is None:
            kwargs[key] = default
    return kwargs

def safe_float(val):
    try:
        return float(val)
    except Exception as e:
        print("❌ safe_float: 轉換失敗，使用預設值 0.0，輸入值：", val, "錯誤：", e, flush=True)
        return 0.0

# ---------------------------
# XGBoost 預測函式
# ---------------------------
def XGboost_recommend1(arr, gender, age):
    le = LabelEncoder()
    labelencoder = LabelEncoder()

    Data = pd.read_csv(PENGHU_ORIGINAL_CSV, encoding='utf-8-sig')
    df_data = pd.DataFrame(
        data=np.c_[Data['weather'], Data['gender'], Data['age'], Data['設置點']],
        columns=['weather', 'gender', 'age', 'label']
    )

    df_data['weather'] = labelencoder.fit_transform(df_data['weather'])

    X = df_data.drop(labels=['label'], axis=1).values
    onehotencoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
    X = onehotencoder.fit_transform(X)
    Y = le.fit_transform(df_data['label'].values)

    arr_labelencode = safe_label_transform(labelencoder, arr, default_value=0)
    if isinstance(arr_labelencode, (list, np.ndarray)):
        arr_labelencode = arr_labelencode[0]
    arr_labelencode = safe_float(arr_labelencode)

    Value_arr = np.array([arr_labelencode, safe_float(gender), safe_float(age)], dtype=np.float64)
    print("🚀 輸入特徵:", Value_arr)

    loaded_model = XGBClassifier()
    loaded_model.load_model(XGB_MODEL1_PATH)
    predicted = loaded_model.predict(Value_arr.reshape(1, -1))
    result = le.inverse_transform(predicted)
    return result[0]

def XGboost_recommend2(arr, gender, age, tidal, temperature, dont_go_here):
    le = LabelEncoder()
    labelencoder = LabelEncoder()

    Data = pd.read_csv(PENGHU_ORIGINAL_CSV, encoding='utf-8-sig')
    df_data = pd.DataFrame(
        data=np.c_[Data['weather'], Data['gender'], Data['age'], Data['tidal'], Data['temperature'], Data['設置點']],
        columns=['weather', 'gender', 'age', 'tidal', 'temperature', 'label']
    )
    df_data = df_data[~df_data['label'].isin(dont_go_here)]

    df_data['weather'] = labelencoder.fit_transform(df_data['weather'])
    df_data[['weather', 'gender', 'age', 'tidal', 'temperature']] = df_data[['weather', 'gender', 'age', 'tidal', 'temperature']].astype(np.float64)

    X = df_data.drop(labels=['label'], axis=1).values
    onehotencoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
    X = onehotencoder.fit_transform(X)
    Y = le.fit_transform(df_data['label'].values)

    arr_labelencode = safe_label_transform(labelencoder, arr, default_value=0)
    if isinstance(arr_labelencode, (list, np.ndarray)):
        arr_labelencode = arr_labelencode[0]

    Value_arr = np.array([
        safe_float(arr_labelencode),
        safe_float(gender),
        safe_float(age),
        safe_float(tidal),
        safe_float(temperature)
    ], dtype=np.float64)
    final = onehotencoder.transform(np.atleast_2d(Value_arr))

    loaded_model = XGBClassifier()
    loaded_model.load_model(XGB_MODEL2_PATH)
    predicted = loaded_model.predict(final)
    result = le.inverse_transform(predicted)
    return result[0]

def XGboost_recommend3(arr, gender, age, tidal, temperature):
    from datetime import datetime as dt
    params = check_and_set_defaults(gender=gender, age=age, tidal=tidal, temperature=temperature)
    gender = safe_float(params['gender'])
    age = safe_float(params['age'])
    tidal = safe_float(params['tidal'])
    temperature = safe_float(params['temperature'])
    if gender < 0:
        gender = 0.0

    print("Now_weather 回傳值: weather =", arr, "temperature =", temperature)
    le = LabelEncoder()
    labelencoder = LabelEncoder()

    Data = pd.read_csv(GENERATED_DATA_CSV, encoding='utf-8-sig')
    print("原始 CSV 檔案內容預覽：")
    print(Data.head())

    df_data = pd.DataFrame(
        data=np.c_[Data['weather'], Data['gender'], Data['age'], Data['tidal'], Data['temperature'], Data['設置點']],
        columns=['weather', 'gender', 'age', 'tidal', 'temperature', 'label']
    )
    for col in ['gender', 'age', 'tidal', 'temperature']:
        df_data[col] = pd.to_numeric(df_data[col], errors='coerce').fillna(0)
    df_data['weather'] = labelencoder.fit_transform(df_data['weather'])
    df_data[['weather', 'gender', 'age', 'tidal', 'temperature']] = df_data[['weather', 'gender', 'age', 'tidal', 'temperature']].astype(np.float64)

    X = df_data.drop(labels=['label'], axis=1).values
    onehotencoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
    X = onehotencoder.fit_transform(X)
    Y = le.fit_transform(df_data['label'].values)

    arr_labelencode = safe_label_transform(labelencoder, arr, default_value=0)
    if isinstance(arr_labelencode, (list, np.ndarray)):
        arr_labelencode = arr_labelencode[0]
    arr_labelencode = safe_float(arr_labelencode)

    Value_arr = np.array([arr_labelencode, gender, age, tidal, temperature], dtype=np.float64)
    print("🚀 輸入特徵 (Value_arr):", Value_arr)

    input_data = np.atleast_2d(Value_arr)
    final = safe_onehot_transform(onehotencoder, input_data)

    loaded_model = XGBClassifier()
    loaded_model.load_model(PHTEST_MODEL_PATH)
    predicted = loaded_model.predict(final)
    result = le.inverse_transform(predicted)
    print("✅ 預測結果:", result[0])
    return result[0]

def XGboost_classification(arr, gender, age, tidal, temperature, arr_msg):
    le = LabelEncoder()
    labelencoder = LabelEncoder()

    if arr_msg == ['永續景點']:
        Data = pd.read_csv(SUSTAINABLE_ATTR_CSV, encoding='utf-8-sig')
        loaded_model = XGBClassifier()
        loaded_model.load_model(SUSTAINABLE_MODEL_PATH)

    if arr_msg == ['一般景點']:
        Data = pd.read_csv(NON_SUSTAINABLE_ATTR_CSV, encoding='utf-8-sig')
        loaded_model = XGBClassifier()
        loaded_model.load_model(NON_SUSTAINABLE_MODEL_PATH)

    if arr_msg == ['永續餐廳']:
        Data = pd.read_csv(SUSTAINABLE_NON_ATTR_CSV, encoding='utf-8-sig')
        loaded_model = XGBClassifier()
        loaded_model.load_model(SUSTAINABLE_NON_MODEL_PATH)

    if arr_msg == ['一般餐廳']:
        Data = pd.read_csv(NON_SUSTAINABLE_NON_ATTR_CSV, encoding='utf-8-sig')
        loaded_model = XGBClassifier()
        loaded_model.load_model(NON_SUSTAINABLE_NON_MODEL_PATH)

    df_data = pd.DataFrame(
        data=np.c_[Data['weather'], Data['gender'], Data['age'], Data['tidal'], Data['temperature'], Data['設置點']],
        columns=['weather', 'gender', 'age', 'tidal', 'temperature', 'label']
    )
    df_data['weather'] = labelencoder.fit_transform(df_data['weather'])
    X = df_data.drop(labels=['label'], axis=1).values
    onehotencoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
    X = onehotencoder.fit_transform(X)
    Y = le.fit_transform(df_data['label'].values)

    arr_labelencode = safe_label_transform(labelencoder, arr, default_value=0)
    if isinstance(arr_labelencode, (list, np.ndarray)):
        arr_labelencode = arr_labelencode[0]

    Value_arr = np.array([
        safe_float(arr_labelencode),
        safe_float(gender),
        safe_float(age),
        safe_float(tidal),
        safe_float(temperature)
    ], dtype=np.float64)
    input_data = np.atleast_2d(Value_arr)
    final = onehotencoder.transform(input_data)
    predicted = loaded_model.predict(final)
    result = le.inverse_transform(predicted)
    return result[0]

# ---------------------------
# 測試部分
# ---------------------------
if __name__ == "__main__":
    weather = Now_weather.weather()
    arr = np.array([weather])
    gender = randrange(0, 2)
    age = randrange(15, 55)
    temperature = Now_weather.temperature()
    tidal = randrange(0, 3)
    print("輸入參數:", arr, gender, age, tidal, temperature)
    print(XGboost_recommend3(arr, gender, age, tidal, temperature))
