# 1. 基礎映像
FROM python:3.11.9-slim

# 2. 建立非 root 使用者（提高安全性）
RUN useradd -m appuser


# 3. 安裝系統套件：build-essential、git、sqlite3、fontconfig，以及 Noto CJK 字型
RUN apt-get update && \
    apt-get install -y \
      build-essential \
      libssl-dev \
      libffi-dev \
      python3-dev \
      git \
      sqlite3 \
      fontconfig \
      fonts-noto-cjk && \
    rm -rf /var/lib/apt/lists/*

# 4. 設定工作目錄
WORKDIR /usr/src/app

# 5. 複製並安裝 Python 相依
COPY requirements.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# 6. 複製程式碼、模型、設定檔
COPY . .

# 7. 調整專案檔案權限
RUN chown -R appuser:appuser /usr/src/app

# 8. 設定環境變數，讓程式知道自己在 Docker 裡面
ENV APP_ENV=docker

# 9. 以 root 執行初始化資料表（確保 SQLite 檔案可寫入）
RUN python init_db.py

# 10. 切換到非 root 使用者
USER appuser

# 11. 開放 8000 端口
EXPOSE 8000

# 12. 啟動 Gunicorn
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4"]
