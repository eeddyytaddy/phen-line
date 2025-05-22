# shared.py
from collections import defaultdict

# 每位使用者對應的語系，預設 zh
user_language: dict[str, str] = defaultdict(lambda: 'zh')

# 每位使用者對應的對話階段
user_stage: dict[str, str]    = defaultdict(lambda: 'ask_language')
