FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY static ./static

# 环境变量在运行平台设置:
#   DROP_PASSWORD  访问密码 (必设! 否则任何人可用你的服务)
#   DROP_MAX_MB    单文件上限 MB (建议 500)
ENV DROP_DIR=/data/downloads \
    DROP_HOST=0.0.0.0 \
    DROP_PORT=7860

VOLUME /data

EXPOSE 7860

CMD ["python", "server.py"]
