# model_trainer.py

import pandas as pd
import numpy as np
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, OneHotEncoder

from config import (
    PENGHU_ORIGINAL_CSV,
    GENERATED_DATA_CSV,
    XGB_MODEL1_PATH,
    XGB_MODEL2_PATH,
    PHTEST_MODEL_PATH,
)

def XGboost_recommend1():
    """
    訓練並儲存第一支 XGBoost 模型，使用原始 penghu_orignal2.csv 資料。
    """
    le = LabelEncoder()
    labelencoder = LabelEncoder()
    tree_deep = 100
    learning_rate = 0.3

    # 讀取原始資料
    Data = pd.read_csv(PENGHU_ORIGINAL_CSV, encoding='utf-8-sig')
    df_data = pd.DataFrame(
        data=np.c_[Data['weather'], Data['gender'], Data['age'], Data['設置點']],
        columns=['weather', 'gender', 'age', 'label']
    )

    # Label Encoding
    df_data['weather'] = labelencoder.fit_transform(df_data['weather'])
    X = df_data.drop(labels=['label'], axis=1).values

    # One-Hot Encoding
    onehot = OneHotEncoder(handle_unknown='ignore', sparse_output=False)
    X = onehot.fit_transform(X)
    Y = df_data['label'].values

    # 切分資料
    X_train, _, Y_train, _ = train_test_split(X, Y, test_size=0.3, random_state=42)
    Y_train = le.fit_transform(Y_train)

    # 訓練模型
    model = XGBClassifier(n_estimators=tree_deep, learning_rate=learning_rate)
    model.fit(X_train, Y_train)

    # 儲存模型
    model.save_model(XGB_MODEL1_PATH)
    print(f"模型已儲存至 {XGB_MODEL1_PATH}")

def XGboost_recommend2():
    """
    訓練並儲存第二支 XGBoost 模型，使用原始 penghu_orignal2.csv 資料含 tidal、temperature 欄位。
    """
    le = LabelEncoder()
    labelencoder = LabelEncoder()
    tree_deep = 100
    learning_rate = 0.3

    Data = pd.read_csv(PENGHU_ORIGINAL_CSV, encoding='utf-8-sig')
    df_data = pd.DataFrame(
        data=np.c_[Data['weather'], Data['gender'], Data['age'], Data['tidal'], Data['temperature'], Data['設置點']],
        columns=['weather', 'gender', 'age', 'tidal', 'temperature', 'label']
    )

    df_data['weather'] = labelencoder.fit_transform(df_data['weather'])
    X = df_data.drop(labels=['label'], axis=1).values

    onehot = OneHotEncoder(handle_unknown='ignore', sparse_output=False)
    X = onehot.fit_transform(X)
    Y = df_data['label'].values

    X_train, _, Y_train, _ = train_test_split(X, Y, test_size=0.3, random_state=42)
    Y_train = le.fit_transform(Y_train)

    model = XGBClassifier(n_estimators=tree_deep, learning_rate=learning_rate)
    model.fit(X_train, Y_train)
    model.save_model(XGB_MODEL2_PATH)
    print(f"模型已儲存至 {XGB_MODEL2_PATH}")
    print('訓練集Accuracy: %.2f%%' % (model.score(X_train, Y_train) * 100.0))

def XGboost_recommend3():
    """
    訓練並儲存第三支 XGBoost 模型，使用 generated_data_updated1.csv。
    """
    le = LabelEncoder()
    labelencoder = LabelEncoder()
    tree_deep = 100
    learning_rate = 0.3

    Data = pd.read_csv(GENERATED_DATA_CSV, encoding='utf-8-sig')
    df_data = pd.DataFrame(
        data=np.c_[Data['weather'], Data['gender'], Data['age'], Data['tidal'], Data['temperature'], Data['設置點']],
        columns=['weather', 'gender', 'age', 'tidal', 'temperature', 'label']
    )

    df_data['weather'] = labelencoder.fit_transform(df_data['weather'])
    X = df_data.drop(labels=['label'], axis=1).values

    onehot = OneHotEncoder(handle_unknown='ignore', sparse_output=False)
    X = onehot.fit_transform(X)
    Y = df_data['label'].values

    X_train, _, Y_train, _ = train_test_split(X, Y, test_size=0.3, random_state=42)
    Y_train = le.fit_transform(Y_train)

    model = XGBClassifier(n_estimators=tree_deep, learning_rate=learning_rate)
    model.fit(X_train, Y_train)
    model.save_model(PHTEST_MODEL_PATH)
    print(f"模型已儲存至 {PHTEST_MODEL_PATH}")

if __name__ == "__main__":
    # 訓練並儲存所有模型
    XGboost_recommend1()
    XGboost_recommend2()
    XGboost_recommend3()
