from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
import pymysql
import csv

def plan2mysql(file):
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
        `no` VARCHAR(50),
        `Time` VARCHAR(50),
        `POI` VARCHAR(50),
        `UserID` VARCHAR(200),
        `設置點` VARCHAR(50),
        `緯度` VARCHAR(50),
        `經度` VARCHAR(50),
        `BPLUID` VARCHAR(50),
        `age` VARCHAR(50),
        `gender` VARCHAR(50),
        `天氣` VARCHAR(50),
        `place_id` VARCHAR(100),
        `crowd` INT,
        `crowd_rank` INT
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
                    no, Time, POI, UserID, 設置點, 緯度, 經度, BPLUID, age, gender, 天氣, place_id, crowd, crowd_rank
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql3, row)

    connection.commit()
    cursor.close()
    connection.close()
    print("CSV data has been saved in MySQL")
