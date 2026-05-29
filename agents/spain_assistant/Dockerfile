FROM python:3.12-slim

# 系统依赖：ca-certificates 用于 HTTPS 抓取，curl-cffi 依赖 libssl
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libssl3 \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先安装依赖（利用 Docker 层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY config.yaml .
COPY src/ src/
COPY assets/ assets/

# 运行时目录（会被 volume 覆盖，这里只是确保首次启动时路径存在）
RUN mkdir -p logs data/raw data/processed public

# 默认命令：启动调度器（常驻运行）
CMD ["python", "src/main.py", "schedule"]
