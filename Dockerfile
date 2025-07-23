# 1. Base image
FROM python:3.11.9-slim

# 2. Create non-root user (retained, but not switched)
RUN useradd -m appuser

# 3. Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential libssl-dev libffi-dev python3-dev \
    git sqlite3 fontconfig fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# 4. Set working directory
WORKDIR /usr/src/app

# 5. Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# 5-1. Install Locust for load testing
RUN pip install --no-cache-dir locust==2.29.0

# 5-2. Add user-site bin to PATH (for root installs)
ENV PATH="/root/.local/bin:${PATH}"

# 6. Copy application code
COPY . .

# 7. Initialize SQLite database (ignore errors if exists)
RUN python init_db.py || true

# 8. Environment variables
ENV APP_ENV=docker \
    PORT=10000 \
    PYTHONUNBUFFERED=1 \
    TEST_MODE=1

# 9. Expose application port
EXPOSE 10000

# 10. Default command: Gunicorn + Gevent with TEST_MODE
CMD sh -c 'python3 -c "from gevent import monkey; monkey.patch_all(); import os; os.environ.setdefault(\"TEST_MODE\", \"1\"); import gunicorn.app.wsgiapp; gunicorn.app.wsgiapp.run()" --bind 0.0.0.0:${PORT} --worker-class gevent --workers 4 --worker-connections 1000 --keep-alive 30 --timeout 180 --preload app:app'
