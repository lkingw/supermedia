FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends aria2 curl cron && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY auto_downloader.py .
COPY entrypoint.sh /entrypoint.sh
COPY update-trackers.sh /update-trackers.sh
RUN chmod +x /entrypoint.sh /update-trackers.sh && mkdir -p /etc/crontabs

RUN mkdir -p /app/data /media

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "/app/auto_downloader.py"]
