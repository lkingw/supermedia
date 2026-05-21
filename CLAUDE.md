# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SuperMedia 是一个全自动的媒体获取与管理系统，通过 Docker Compose 编排三个服务：

1. **crawler** — Python 爬虫，定时爬取指定 URL 页面，提取磁力链接写入 `data/magnet.txt`
2. **downloader** — Python 下载守护进程，读取 `data/magnet.txt`，通过 aria2c 并行下载到 `media/`
3. **jellyfin** — 流媒体服务，读取 `media/` 提供播放

## Remote Server Deployment

- **Server IP**: `192.168.1.202`
- **SSH User**: `more`
- **SSH Password**: ``
- **Docker Compose Location**: `/home/more/supermedia/`
- **Deploy**: `cd /home/more/supermedia && git pull && docker compose build task-manager && docker compose up -d task-manager`
- **Logs**: `docker logs -f task-manager`
- **All services**: `docker compose up -d --build`

## Commands

- **启动所有服务**: `docker compose up -d`
- **查看日志**: `docker compose logs -f`
- **停止所有服务**: `docker compose down`
- **重新构建**: `docker compose build --no-cache`
- **配置爬虫 URL**: 编辑 `data/config/urls.txt`
- **修改配置**: 编辑 `.env`

## Architecture

```
supermedia/
├── docker-compose.yml
├── .env
├── crawler/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── crawler.py              # 爬虫：requests + BeautifulSoup + schedule
├── downloader/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── auto_downloader.py      # 下载器：aria2c + ThreadPoolExecutor
├── data/
│   ├── magnet.txt              # 任务队列（爬虫写，下载器读）
│   ├── completed.txt           # 完成记录（下载器写）
│   └── config/
│       └── urls.txt            # 种子 URL 列表
└── media/
    ├── movies/
    ├── tv/
    └── music/
```

### Data Flow

```
urls.txt → crawler → magnet.txt → downloader → /media → jellyfin
```

### Network

- **downloader**: `network_mode: host`（P2P 下载需要开放大量端口）
- **crawler**: bridge 网络（仅需 HTTP 出站）
- **jellyfin**: bridge + 端口映射 8096

## Configuration

所有配置通过 `.env` 环境变量管理：

| Variable | Default | Description |
|---|---|---|
| `CRAWL_INTERVAL` | `6h` | 爬虫调度间隔 |
| `CRAWL_DEPTH` | `1` | 爬取深度 |
| `MAX_PARALLEL` | `5` | 最大并发下载数 |
| `CHECK_INTERVAL` | `10` | 下载器轮询间隔（秒） |
| `JELLYFIN_PORT` | `8096` | Jellyfin Web 端口 |

## Key Design Decisions

- **文件通信**：爬虫和下载器通过共享卷 `./data` 中的 `magnet.txt` 通信，简单可靠
- **追加写入**：爬虫 append 写入，下载器通过 `completed.txt` 去重，无竞态风险
- **去重**：爬虫同时读取 `magnet.txt` 和 `completed.txt` 避免重复
- **同域名限制**：爬虫链接跟随仅限同域名，防止爬到外部网站
- **host 网络**：downloader 使用 host 模式确保 P2P 连接性
