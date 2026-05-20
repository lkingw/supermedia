#!/bin/bash
# 更新 trackers 的 cron 脚本（每日 03:00 执行）

TRACKERS_FILE="${TRACKERS_FILE:-/app/data/trackers.txt}"
TRACKERS_URL="${TRACKERS_URL:-https://raw.githubusercontent.com/adysec/tracker/main/trackers_best_udp.txt}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始更新 trackers..."
if curl -sL --max-time 60 "$TRACKERS_URL" -o "$TRACKERS_FILE.tmp"; then
    if [ -s "$TRACKERS_FILE.tmp" ]; then
        mv "$TRACKERS_FILE.tmp" "$TRACKERS_FILE"
        lines=$(grep -v '^#' "$TRACKERS_FILE" | grep -v '^$' | wc -l)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Trackers 更新成功，共 ${lines} 条"
    else
        rm -f "$TRACKERS_FILE.tmp"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️  下载内容为空"
    fi
else
    rm -f "$TRACKERS_FILE.tmp"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ 下载失败"
fi
