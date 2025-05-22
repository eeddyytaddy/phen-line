import csv
def get_location(file):
    with open(file, 'r', newline='', encoding='utf-8') as file:
        reader = csv.reader(file)
        for row in reader:
            address = row[0]  # 獲取地址
            latitude = float(row[1])  # 獲取纬度（轉為浮点数）
            longitude = float(row[2])  # 獲取经度（轉為浮点数）
    # print(latitude,longitude)
    return latitude,longitude

#print(get_location('C:/Users/roy88/testproject/python/PH/locations.csv'))