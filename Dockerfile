# ------------------------------------------------------------
# 1. 基礎映像
# ------------------------------------------------------------
FROM python:3.11.9-slim

# ------------------------------------------------------------
# 2. 參數：決定最後是否切換到非 root
#    預設 MODE=web  →  USER appuser
#    若   MODE=locust → 保持 root
# ------------------------------------------------------------
ARG MODE=web

# 3. 建立非 root 使用者
RUN useradd -m appuser

# ------------------------------------------------------------
# 4. 安裝系統套件
# ------------------------------------------------------------
RUN apt-get update && \
    apt-get install -y \
      build-essential libssl-dev libffi-dev python3-dev \
      git sqlite3 fontconfig fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------
# 5. 設定工作目錄
# ------------------------------------------------------------
WORKDIR /usr/src/app

# ------------------------------------------------------------
# 6. 安裝 Python 依賴
# ------------------------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ------------------------------------------------------------
# 7. 複製程式碼
# ------------------------------------------------------------
COPY . .

# 8. SQLite 初始化（若已存在則忽略）
RUN python init_db.py || true

# ------------------------------------------------------------
# 9. 切換使用者 (僅在 MODE=web 時)
# ------------------------------------------------------------
RUN if [ "$MODE" = "web" ]; then chown -R appuser:appuser /usr/src/app; fi

# 預設 CMD 只是一個 placeholder，後續會被 Railway 的
# Custom Start Command 覆蓋；這裡放 sleep 避免立刻退出
CMD ["sleep", "infinity"]

# 若 MODE=web，最後加上 USER appuser
# 這行必須寫在最後，才能依 ARG 真正覆蓋
RUN if [ "$MODE" = "web" ]; then echo "Switch to appuser"; \
    sed -i '$a USER appuser' $(basename "$0"); fi
