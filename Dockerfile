# 1. Base image
FROM python:3.11.9-slim

# 2. Create non‑root user for better security
RUN useradd -m appuser

# 3. Install system packages
RUN apt-get update && apt-get install -y \
    build-essential libssl-dev libffi-dev python3-dev git sqlite3 \
    fontconfig fonts-noto-cjk && \
    rm -rf /var/lib/apt/lists/*

# 4. Set working directory
WORKDIR /usr/src/app

# 5. Copy and install Python dependencies first (separate cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 6. Copy application source code
COPY . .

# 7. Fix permissions for non‑root user
RUN chown -R appuser:appuser /usr/src/app

# 8. Environment variables
ENV APP_ENV=docker \
    PORT=10000 \
    PYTHONUNBUFFERED=1

# 9. Initialize SQLite database (ignore error if already exists)
RUN python init_db.py || true

# 10. Switch to non‑root user
USER appuser

# 11. Expose default port
EXPOSE 10000

# 12. Launch Gunicorn
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:$PORT", "--workers", "1", "--threads", "4"]
