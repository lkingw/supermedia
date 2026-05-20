# 任务3：创建 Docker Compose 编排

## 目标

创建 `docker-compose.yml` 和 `.env` 文件，编排 crawler、downloader、jellyfin 三个服务。

## 对话上下文

- 项目：SuperMedia — 自动爬取磁力链接并下载，构建 Jellyfin 媒体仓库
- 设计文档：`docs/superpowers/specs/2026-05-20-docker-compose-orchestration-design.md`
- 关键决策：
  - 三容器方案：crawler + downloader + jellyfin
  - downloader 使用 `network_mode: host`（P2P 下载需要开放大量端口）
  - crawler 使用 bridge 网络
  - jellyfin 使用 bridge + 端口映射 8096
  - 共享卷：`./data`（爬虫和下载器通信）、`./media`（下载输出 + Jellyfin 媒体库）
  - 重启策略：`unless-stopped`
  - 环境变量通过 `.env` 文件管理

## 实现步骤

### 1. 创建 `.env` 文件

```env
CRAWL_INTERVAL=6h
CRAWL_DEPTH=1
MAX_PARALLEL=5
CHECK_INTERVAL=10
JELLYFIN_PORT=8096
```

### 2. 创建 `docker-compose.yml`

```yaml
services:
  crawler:
    build: ./crawler
    volumes:
      - ./data:/app/data
    env_file: .env
    restart: unless-stopped
    depends_on:
      - downloader

  downloader:
    build: ./downloader
    network_mode: host
    volumes:
      - ./data:/app/data
      - ./media:/media
    env_file: .env
    restart: unless-stopped

  jellyfin:
    image: jellyfin/jellyfin:latest
    ports:
      - "${JELLYFIN_PORT}:8096"
    volumes:
      - ./media:/media:ro
      - jellyfin_config:/config
      - jellyfin_cache:/cache
    restart: unless-stopped

volumes:
  jellyfin_config:
  jellyfin_cache:
```

### 3. 创建 `data/` 目录结构

```
data/
├── config/
│   └── urls.txt    # 示例 URL 列表
└── magnet.txt      # 空文件，占位
```

### 4. 创建 `media/` 目录

空目录，用于存放下载的媒体文件。

### 5. 创建 `.dockerignore`

排除不需要的文件：`docs/`、`.env`（敏感信息）、`data/`、`media/` 等。

### 6. 更新 `readme.md`

更新 README 中的快速开始部分，添加 Docker Compose 部署说明。

## 验证标准

- [ ] `docker compose build` 可成功构建所有镜像
- [ ] `docker compose up -d` 可启动所有服务
- [ ] 共享卷挂载正确，文件通信正常
- [ ] downloader 使用 host 网络模式
- [ ] Jellyfin 可通过 8096 端口访问
- [ ] `.env` 环境变量正确传递到容器
- [ ] 服务重启后自动恢复
