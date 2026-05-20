# 任务1：重构下载器为 Docker 适配版本

## 目标

将现有的 `auto_downloader.py` 从项目根目录迁移到 `downloader/` 子目录，并适配 Docker 容器化运行。

## 对话上下文

- 项目：SuperMedia — 自动爬取磁力链接并下载，构建 Jellyfin 媒体仓库
- 设计文档：`docs/superpowers/specs/2026-05-20-docker-compose-orchestration-design.md`
- 关键决策：
  - downloader 使用 `network_mode: host`（P2P 下载需要开放大量端口）
  - 基础镜像：`python:3.11-slim`
  - 文件通信：通过共享卷 `./data` 读写 `magnet.txt` 和 `completed.txt`
  - 下载输出到 `/media` 目录
  - 重启策略：`unless-stopped`

## 实现步骤

### 1. 创建 `downloader/` 目录结构

```
downloader/
├── Dockerfile
├── requirements.txt
└── auto_downloader.py
```

### 2. 迁移并重构 `auto_downloader.py`

- 将 `auto_downloader.py` 从项目根目录复制到 `downloader/`
- 修改路径常量，支持环境变量配置：
  - `MAGNET_FILE` → 从环境变量 `MAGNET_FILE` 读取，默认 `/app/data/magnet.txt`
  - `SAVE_PATH` → 从环境变量 `SAVE_PATH` 读取，默认 `/media`
  - `COMPLETED_FILE` → 从环境变量 `COMPLETED_FILE` 读取，默认 `/app/data/completed.txt`
  - `MAX_PARALLEL` → 从环境变量 `MAX_PARALLEL` 读取，默认 `5`
  - `CHECK_INTERVAL` → 从环境变量 `CHECK_INTERVAL` 读取，默认 `10`
- 使用 `os.environ.get()` 实现环境变量覆盖

### 3. 创建 `downloader/requirements.txt`

- 当前仅依赖 Python 标准库，`requirements.txt` 为空文件（预留将来依赖）

### 4. 创建 `downloader/Dockerfile`

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y aria2 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY auto_downloader.py .
CMD ["python", "auto_downloader.py"]
```

### 5. 清理根目录

- 删除根目录下的 `auto_downloader.py`（已迁移到 `downloader/`）

## 验证标准

- [ ] `downloader/auto_downloader.py` 支持环境变量配置
- [ ] `downloader/Dockerfile` 可成功构建
- [ ] 容器内 aria2c 可用
- [ ] 路径默认值适配容器内挂载点（`/app/data/`、`/media`）
