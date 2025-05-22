import csv

def search_for_location(file, keyword):
    matching_rows = []
    with open(file, mode='r', newline='', encoding='utf-8-sig') as csvfile:
        reader = csv.reader(csvfile)
        header = next(reader)  # 跳过头部行
        for row in reader:
            if keyword in row:  # 检查关键字是否在当前行中
                matching_rows.append(row)  # 如果关键字匹配，则将当前行添加到匹配列表中
    for row in matching_rows:
        latitude = row[5] 
        longitude = row[6]  
    return latitude,longitude

#print(search_for_location('C:/Users/roy88/testproject/python/linebot/ph/plan.csv', '天津蔥抓餅'))

def name_list(file):  
    with open(file, mode='r', newline='', encoding='utf-8-sig') as file:
        reader = csv.reader(file)
        next(reader)  # 跳過標頭行
        name_list=[]
        rows = list(reader)
        n = min(10, len(rows))
        i = 1
        for row in rows:
            name_list.append(row[4])
            
            if i == n:
                break
            i += 1
    return name_list

#print(name_list('C:/Users/roy88/testproject/python/linebot/ph/plan.csv'))