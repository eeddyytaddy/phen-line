# ------------------------------------------------------------
# 1 基礎映像
# ------------------------------------------------------------
FROM python:3.11.9-slim

# ------------------------------------------------------------
# 2 參數：決定是否以 root 執行
#    build-arg RUN_AS_ROOT=true  -> root
#    build-arg RUN_AS_ROOT=false -> 切換 appuser（預設）
# ------------------------------------------------------------
ARG RUN_AS_ROOT=false

# 3 建立非 root 使用者
RUN useradd -m appuser

# 4 安裝系統套件
RUN apt-get update && \
    apt-get install -y \
      build-essential git sqlite3 \
      libssl-dev libffi-dev python3-dev \
      fontconfig fonts-noto-cjk && \
    rm -rf /var/lib/apt/lists/*

# 5 工作目錄
WORKDIR /usr/src/app

# 6 安裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 7 複製程式碼
COPY . .

# 8 初始化 SQLite（失敗不終止）
RUN python init_db.py || true

# 9 依 RUN_AS_ROOT 決定是否切換使用者
#    *true*  -> 保持 root
#    *false* -> chown + USER appuser
RUN if [ "$RUN_AS_ROOT" = "false" ]; then \
       chown -R appuser:appuser /usr/src/app && \
       echo "switching to appuser"; \
    fi

# 如果要切非 root，就在這裡 USER appuser
# （Docker 允許 USER 指令多次出現，最後一條生效）
USER ${RUN_AS_ROOT:+root}${RUN_AS_ROOT:=appuser}

# 10 預設 CMD 會被 Railway Custom Start Command 蓋掉
CMD ["sleep", "infinity"]
