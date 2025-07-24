# boot.py

# 1. gevent 最全面的 monkey‐patch
from gevent import monkey
monkey.patch_all()

# 2. 砍掉 threading 內建的 _after_fork 與 Thread._stop
import threading
threading._after_fork      = lambda *a, **k: None
threading.Thread._stop     = lambda self: None

# 3. 再去 import 你的 Flask app
from app import app as application
