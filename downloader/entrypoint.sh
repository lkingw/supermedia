#!/bin/bash
# Entrypoint 脚本：下载 trackers + 启动 cron 定时更新 + 运行下载器

set -e

TRACKERS_FILE="${TRACKERS_FILE:-/app/data/trackers.txt}"
TRACKERS_URL="${TRACKERS_URL:-https://raw.githubusercontent.com/adysec/tracker/main/trackers_best.txt}"

echo "📥 启动 trackers 自动更新服务..."

# 立即下载一次
if curl -sL --max-time 30 "$TRACKERS_URL" -o "$TRACKERS_FILE.tmp"; then
    if [ -s "$TRACKERS_FILE.tmp" ]; then
        mv "$TRACKERS_FILE.tmp" "$TRACKERS_FILE"
        lines=$(grep -v '^#' "$TRACKERS_FILE" | grep -v '^$' | wc -l)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Trackers 更新成功，共 ${lines} 条"
    else
        rm -f "$TRACKERS_FILE.tmp"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️  下载内容为空，保留旧文件"
    fi
else
    rm -f "$TRACKERS_FILE.tmp"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️  下载失败，保留旧 trackers"
fi

# 设置每日凌晨 3 点更新 trackers 的 cron 任务
echo "0 3 * * * /update-trackers.sh >> /var/log/tracker_update.log 2>&1" > /etc/crontabs/root

# 启动 cron 后台运行（Debian 中二进制名为 cron）
echo "⏰ Cron 已设置，每日 03:00 更新 trackers"
cron &

# 等待 cron 进程启动
sleep 1

# 启动下载守护进程
echo "🚀 启动下载守护进程..."
exec python /app/auto_downloader.py
