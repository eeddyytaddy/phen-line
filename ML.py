from xgboost import XGBClassifier
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, OneHotEncoder

from config import (
    PENGHU_ORIGINAL_CSV,
    GENERATED_DATA_CSV,
)

def XGboost_recommend1(arr, gender, age):
    le = LabelEncoder()
    labelencoder = LabelEncoder()
    tree_deep = 100
    learning_rate = 0.3

    Data = pd.read_csv(PENGHU_ORIGINAL_CSV, encoding='utf-8-sig')
    df_data = pd.DataFrame(
        data=np.c_[Data['weather'], Data['gender'], Data['age'], Data['設置點']],
        columns=['weather', 'gender', 'age', 'label']
    )

    df_data['weather'] = labelencoder.fit_transform(df_data['weather'])
    X = df_data.drop(labels=['label'], axis=1).values
    onehotencoder = OneHotEncoder(handle_unknown='ignore', sparse_output=False)
    X = onehotencoder.fit_transform(X)
    Y = df_data['label'].values

    X_train, X_test, Y_train, Y_test = train_test_split(
        X, Y, test_size=0.3, random_state=42
    )
    Y_train = le.fit_transform(Y_train)

    arr_labelencode = labelencoder.transform(arr)
    Value_arr = np.array([arr_labelencode[0], gender, age], dtype=np.float64)
    final = onehotencoder.transform(Value_arr.reshape(1, -1))

    xgboostModel = XGBClassifier(n_estimators=tree_deep, learning_rate=learning_rate)
    xgboostModel.fit(X_train, Y_train)

    predicted = xgboostModel.predict(final)
    result = le.inverse_transform(predicted)
    return predicted, result

def XGboost_recommend2(arr, gender, age, tidal, temperature):
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

    onehotencoder = OneHotEncoder(handle_unknown='ignore', sparse_output=False)
    X = onehotencoder.fit_transform(X)
    Y = df_data['label'].values

    X_train, X_test, Y_train, Y_test = train_test_split(
        X, Y, test_size=0.3, random_state=42
    )
    Y_train = le.fit_transform(Y_train)

    arr_labelencode = labelencoder.transform(arr)
    Value_arr = np.array([arr_labelencode[0], gender, age, tidal, temperature], dtype=np.float64)
    final = onehotencoder.transform(Value_arr.reshape(1, -1))

    xgboostModel = XGBClassifier(n_estimators=tree_deep, learning_rate=learning_rate)
    xgboostModel.fit(X_train, Y_train)

    predicted = xgboostModel.predict(final)
    result = le.inverse_transform(predicted)
    return result[0]

def XGboost_recommend3(arr, gender, age, tidal, temperature, dont_go_here):
    from sklearn.preprocessing import LabelEncoder, OneHotEncoder

    tree_deep = 100
    learning_rate = 0.3

    Data = pd.read_csv(GENERATED_DATA_CSV, encoding='utf-8-sig')
    df_data = pd.DataFrame(
        data=np.c_[Data['weather'], Data['gender'], Data['age'], Data['tidal'], Data['temperature'], Data['設置點']],
        columns=['weather', 'gender', 'age', 'tidal', 'temperature', 'label']
    )
    df_data = df_data[~df_data['label'].isin(dont_go_here)]
    for col in ['gender', 'age', 'tidal', 'temperature']:
        df_data[col] = pd.to_numeric(df_data[col], errors='coerce').fillna(0)

    labelencoder = LabelEncoder()
    df_data['weather'] = labelencoder.fit_transform(df_data['weather'])
    X = df_data.drop(labels=['label'], axis=1).values
    onehotencoder = OneHotEncoder(handle_unknown='ignore', sparse_output=False)
    X = onehotencoder.fit_transform(X)
    Y = df_data['label'].values
    le = LabelEncoder()
    Y = le.fit_transform(Y)

    X_train, X_test, Y_train, Y_test = train_test_split(
        X, Y, test_size=0.3, random_state=42
    )

    arr_labelencode = labelencoder.transform(arr)
    Value_arr = np.array([
        float(arr_labelencode[0]), float(gender),
        float(age), float(tidal), float(temperature)
    ], dtype=np.float64)
    final = onehotencoder.transform(Value_arr.reshape(1, -1))

    xgboostModel = XGBClassifier(n_estimators=tree_deep, learning_rate=learning_rate)
    xgboostModel.fit(X_train, Y_train)
    xgboostModel.save_model('PHtest.bin')

    predicted = xgboostModel.predict(final)
    result = le.inverse_transform(predicted)
    return result[0]

def XGboost_plan(plan_data, gender, age):
    le = LabelEncoder()
    tree_deep = 100
    learning_rate = 0.3

    df_data = pd.DataFrame(
        data=np.c_[plan_data['gender'], plan_data['age'], plan_data['UserID/MemID']],
        columns=['gender', 'age', 'label']
    )
    X_train = df_data.drop(labels=['label'], axis=1).values
    Y_train = le.fit_transform(df_data['label'].values)

    xgboostModel = XGBClassifier(n_estimators=tree_deep, learning_rate=learning_rate)
    xgboostModel.fit(X_train, Y_train)

    test = np.array([gender, age]).reshape(1, -1)
    predicted = xgboostModel.predict(test)
    result = le.inverse_transform(predicted)
    return result[0]
