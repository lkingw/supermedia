# Docker Compose 编排设计

## 概述

SuperMedia 采用三容器 Docker Compose 编排方案，通过共享卷实现组件间文件通信，部署在本地/NAS 环境，提供全自动的磁力链接爬取、下载和 Jellyfin 媒体播放服务。

## 目录结构

```
supermedia/
├── docker-compose.yml
├── .env                        # 环境变量配置
├── crawler/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── crawler.py              # 爬虫主程序
├── downloader/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── auto_downloader.py      # 下载守护进程
├── data/                       # 共享数据目录（bind mount）
│   ├── magnet.txt              # 爬虫写入，下载器读取
│   ├── completed.txt           # 下载器写入完成记录
│   └── config/
│       └── urls.txt            # 爬虫的目标 URL 列表
└── media/                      # 下载输出 + Jellyfin 媒体库
```

## 容器编排

### 服务定义

| 服务 | 镜像 | 网络模式 | 关键配置 |
|------|------|----------|----------|
| `crawler` | 自建（Python 3.11） | bridge | 挂载 `./data` 读写，定时任务调度 |
| `downloader` | 自建（Python 3.11 + aria2c） | host | 挂载 `./data` 读写 + `./media` 读写，常驻守护进程 |
| `jellyfin` | `jellyfin/jellyfin:latest` | bridge + 端口映射 8096 | 挂载 `./media` 只读 |

### 网络模式说明

- **downloader 使用 host 模式**：P2P 下载（BT/DHT）需要开放大量随机端口，host 模式避免 NAT 和端口映射问题，确保最佳连接性
- **crawler 使用 bridge 模式**：仅需 HTTP 出站请求，无需特殊端口
- **jellyfin 使用 bridge + 端口映射**：Web 服务，只需暴露 HTTP 端口 8096

### 共享卷挂载

| 宿主机路径 | 容器 | 挂载点 | 权限 |
|-----------|------|--------|------|
| `./data` | crawler | `/app/data` | 读写 |
| `./data` | downloader | `/app/data` | 读写 |
| `./media` | downloader | `/media` | 读写 |
| `./media` | jellyfin | `/media` | 只读 |

### 重启策略

所有服务使用 `restart: unless-stopped`，确保 NAS 重启后自动恢复。

## 数据流

```
urls.txt → crawler 读取 → 爬取页面 → 提取磁力链接 → 追加写入 magnet.txt
magnet.txt → downloader 读取 → aria2c 下载 → 写入 /media + completed.txt
/media → jellyfin 扫描 → 提供播放
```

## 爬虫调度

容器内使用 Python `schedule` 库实现定时调度，默认每 6 小时爬取一次。调度间隔通过环境变量 `CRAWL_INTERVAL` 配置。

## 文件竞态处理

- 爬虫采用**追加写入**模式（append），不覆盖已有内容
- 下载器读取后不删除 `magnet.txt` 中的行，通过 `completed.txt` 去重
- 两者不会同时写同一文件，无竞态风险

## 错误处理

- **下载失败**：打印错误日志，不记录到 `completed.txt`，下次轮询自动重试
- **爬虫失败**：打印错误日志，等待下次调度周期重试
- **aria2c 缺失**：Dockerfile 中确保安装，构建时即验证

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CRAWL_INTERVAL` | `6h` | 爬虫调度间隔 |
| `CRAWL_DEPTH` | `1` | 爬取深度 |
| `MAX_PARALLEL` | `5` | 最大并发下载数 |
| `CHECK_INTERVAL` | `10` | 下载器轮询间隔（秒） |
| `JELLYFIN_PORT` | `8096` | Jellyfin Web 端口 |

## Dockerfile 设计

### downloader/Dockerfile

- 基础镜像：`python:3.11-slim`
- 安装 aria2c（`apt-get install aria2`）
- 复制 `auto_downloader.py` + `requirements.txt`
- 入口：`python auto_downloader.py`

### crawler/Dockerfile

- 基础镜像：`python:3.11-slim`
- 安装爬虫依赖（requests、beautifulsoup4 等）
- 复制 `crawler.py` + `requirements.txt`
- 入口：`python crawler.py`

## 决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 通信方式 | 文件共享（magnet.txt） | 和现有代码一致，改动最小，本地部署竞态风险极低 |
| downloader 网络模式 | host | P2P 下载需要开放大量端口，避免 NAT 问题 |
| 基础镜像 | python:3.11-slim | 用户指定，稳定且体积小 |
| 爬虫调度 | Python schedule 库 | 轻量级，无需额外依赖（如 cron） |
| 重启策略 | unless-stopped | NAS 场景下确保服务自动恢复 |
