# ---- STAGE 1: Builder (Build Dependencies and Wheels) ----
# 使用標準映像檔以確保包含編譯工具 (如 build-essential)
FROM python:3.11.9 AS builder

# 設置工作目錄
WORKDIR /usr/src/app

# 安裝構建和運行所需的系統依賴
# 這裡包含編譯 Python 套件所需的工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libssl-dev libffi-dev python3-dev \
    sqlite3 git \
 && rm -rf /var/lib/apt/lists/*

# 複製並安裝所有 Python 依賴
COPY requirements.txt .
# 下載並安裝依賴，將輪子文件 (wheels) 存儲在本地，以便下一階段離線安裝
# 這裡只需要使用 pip wheel 處理 requirements.txt 即可
RUN pip install --upgrade pip \
 && pip wheel --wheel-dir /usr/src/app/wheels -r requirements.txt

# ---- STAGE 2: Runtime (Minimal Execution Image) ----
# 使用更小的 slim 映像檔作為最終運行環境
FROM python:3.11.9-slim AS runtime

# 設置非 root 用戶 (與原始文件保持一致)
# 創建非 root 用戶，使用穩定的 UID/GID for K8s volumes
RUN useradd -m -u 1000 appuser

# 僅安裝運行所需的最小系統依賴 (例如 SQLite 和字型)
# fontconfig 和 fonts-noto-cjk 確保中文顯示正常
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 fontconfig fonts-noto-cjk \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app

# 從 builder 階段複製已編譯的 Python 輪子
COPY --from=builder /usr/src/app/wheels /wheels/

# 【修正 BUG】：將 requirements.txt 提前複製到 runtime 映像檔中
COPY requirements.txt .

# 離線安裝所有 Python 依賴 (requirements.txt, 應包含 Flask, gunicorn, gevent)
# 從 builder 階段複製的 /wheels 目錄中尋找並安裝，避免網絡下載和編譯。
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --find-links=/wheels -r requirements.txt \
 && rm -rf /wheels

# 複製應用程式碼 (app.py, templates/ 等其他應用程式文件)
COPY . .

# Writable data dir for SQLite / temp files
# 確保 appuser 對數據和應用程式目錄有寫入權限
RUN mkdir -p /data && chown -R appuser:appuser /usr/src/app /data

# Sensible defaults; override via envs in K8s (與原始文件保持一致)
ENV APP_ENV=docker \
    PORT=8000 \
    PYTHONUNBUFFERED=1 \
    D1_BINDING=/data/app.db \
    GUNICORN_WORKERS=2 \
    GUNICORN_TIMEOUT=30

EXPOSE 8000
USER appuser

# Docker healthcheck (與原始文件保持一致)
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
 CMD python -c "import os,sys,urllib.request as u; url='http://127.0.0.1:'+os.environ.get('PORT','8000')+'/healthz'; sys.exit(0 if u.urlopen(url).getcode()==200 else 1)"

# Run in production with Gunicorn + gevent (與原始文件保持一致)
CMD ["sh","-c","exec gunicorn -k gevent -w ${GUNICORN_WORKERS} -b 0.0.0.0:${PORT} app:app --timeout ${GUNICORN_TIMEOUT} --access-logfile - --error-logfile -"]
