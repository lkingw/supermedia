FROM python:3.11-slim

WORKDIR /app

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制爬虫脚本
COPY crawler.py .

# 启动爬虫
CMD ["python", "crawler.py"]
