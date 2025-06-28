import sqlite3, os
db = os.getenv("LOCUST_DB", "locust_stats.db")
con = sqlite3.connect(db)
for row in con.execute("SELECT ts, typeof(ts) FROM locust_stats LIMIT 5"):
    print(row)
