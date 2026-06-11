from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
import pymysql
import csv

def plan3mysql(file):
    connection = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset='utf8'
    )

    cursor = connection.cursor()

    # 若 plan 表存在則刪除
    sql1 = "DROP TABLE IF EXISTS `plan`;"
    cursor.execute(sql1)

    # 新建 plan 表，加入 crowd_rank 欄位
    sql2 = '''
    CREATE TABLE `plan`(
       id INT AUTO_INCREMENT PRIMARY KEY,
        crowd_level INT COMMENT '人潮等級 1-5',
        is_student INT COMMENT '1:學生, 0:非學生',
        gender VARCHAR(10) COMMENT 'Male, Female, Other',
        is_weekend INT COMMENT '1:假日, 0:平日',
        is_festival INT COMMENT '1:節慶, 0:平日',
        weather VARCHAR(20) COMMENT '天氣狀態',
        temperature FLOAT COMMENT '氣溫',
        preference FLOAT COMMENT '喜好程度 (Target)'
    );
    '''
    cursor.execute(sql2)

    with open(file, mode='r', newline='', encoding='utf-8-sig') as file_obj:
        reader = csv.reader(file_obj)
        # 跳過標題列
        next(reader)
        for row in reader:
            # row 的欄位數量需要對應 CSV 順序；若 CSV 的欄位依序為
            # no, Time, POI, UserID, 設置點, 緯度, 經度, BPLUID, age, gender, 天氣, place_id, crowd, crowd_rank
            # 則插入語句如下：
            sql3 = """
                INSERT INTO `plan` (
                    no, Time, POI, UserID, 設置點, 緯度, 經度, BPLUID, age, gender, 天氣, place_id, crowd,distance, crowd_rank
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s)
            """
            cursor.execute(sql3, row)

    connection.commit()
    cursor.close()
    connection.close()
    print("CSV data has been saved in MySQL")
