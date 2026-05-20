# SuperMedia

自动爬取磁力链接并下载，构建 Jellyfin 媒体仓库。

## 项目愿景

SuperMedia 旨在实现一个全自动的媒体获取与管理系统，通过 Docker Compose 一键部署：

| 组件 | 职责 |
|------|------|
| **爬虫** | 定时爬取指定 URL 列表和深度的页面，提取磁力链接写入任务队列 |
| **下载器** | 监听任务队列，通过 aria2c 并行下载磁力链接到媒体目录 |
| **Jellyfin** | 读取媒体目录，提供流媒体播放服务 |

## 当前状态

- ✅ 下载器守护进程 — 监听 `magnet.txt`，通过 aria2c 并行下载
- ✅ 爬虫模块 — 定时爬取页面，提取磁力链接
- ✅ Docker Compose 编排 — 三容器一键部署
- ✅ Jellyfin 集成 — 媒体库自动扫描播放

## 快速开始

### 前置依赖

- Docker + Docker Compose

### 部署

```bash
# 克隆项目
git clone <repo-url> supermedia && cd supermedia

# 配置爬虫目标 URL
vim data/config/urls.txt

# 修改环境变量（可选）
vim .env

# 一键启动
docker compose up -d

# 查看日志
docker compose logs -f
```

启动后访问 `http://<host>:8096` 完成 Jellyfin 初始化设置。

## 环境变量

通过 `.env` 文件配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CRAWL_INTERVAL` | `6h` | 爬虫调度间隔（支持 `30m`、`1h`、`6h` 等） |
| `CRAWL_DEPTH` | `1` | 爬取深度 |
| `MAX_PARALLEL` | `5` | 最大并发下载数 |
| `CHECK_INTERVAL` | `10` | 下载器轮询间隔（秒） |
| `JELLYFIN_PORT` | `8096` | Jellyfin Web 端口 |

## 项目结构

```
supermedia/
├── docker-compose.yml          # Docker Compose 编排
├── .env                        # 环境变量配置
├── crawler/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── crawler.py              # 爬虫主程序
├── downloader/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── auto_downloader.py      # 下载守护进程
├── data/
│   ├── magnet.txt              # 磁力链接任务队列
│   ├── completed.txt           # 已完成记录
│   └── config/
│       └── urls.txt            # 爬虫目标 URL 列表
└── media/
    ├── movies/                 # 电影
    ├── tv/                     # 电视剧
    └── music/                  # 音乐
```

## 数据流

```
urls.txt → crawler 爬取 → magnet.txt → downloader 下载 → /media → jellyfin 播放
```
