from collections import defaultdict

# 原有
user_language: dict[str, str] = defaultdict(lambda: 'zh')
user_stage:    dict[str, str] = defaultdict(lambda: 'ask_language')

# 新增：每位使用者的專屬狀態
user_age:         dict[str, int | None]    = defaultdict(lambda: None)
user_gender:      dict[str, str | None]    = defaultdict(lambda: None)
user_trip_days:   dict[str, str | None]    = defaultdict(lambda: None)
user_preparing:   dict[str, bool]          = defaultdict(lambda: False)
user_plan_ready:  dict[str, bool]          = defaultdict(lambda: False)
user_location = {}
