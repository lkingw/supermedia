# 任务2：实现爬虫模块

## 目标

实现 Python 爬虫模块，定时爬取指定 URL 列表和深度的页面，提取磁力链接并追加写入 `magnet.txt`。

## 对话上下文

- 项目：SuperMedia — 自动爬取磁力链接并下载，构建 Jellyfin 媒体仓库
- 设计文档：`docs/superpowers/specs/2026-05-20-docker-compose-orchestration-design.md`
- 关键决策：
  - 技术栈：Python 3.11
  - 调度方式：Python `schedule` 库，默认每 6 小时爬取一次
  - 通信方式：追加写入 `/app/data/magnet.txt`
  - 目标 URL 列表：从 `/app/data/config/urls.txt` 读取
  - 爬取深度：通过环境变量 `CRAWL_DEPTH` 配置，默认 `1`
  - 调度间隔：通过环境变量 `CRAWL_INTERVAL` 配置，默认 `6h`
  - 错误处理：打印错误日志，等待下次调度周期重试
  - 基础镜像：`python:3.11-slim`

## 实现步骤

### 1. 创建 `crawler/` 目录结构

```
crawler/
├── Dockerfile
├── requirements.txt
└── crawler.py
```

### 2. 实现 `crawler/crawler.py`

核心功能：
- **URL 加载**：从 `/app/data/config/urls.txt` 读取目标 URL 列表（每行一个 URL）
- **页面爬取**：使用 `requests` + `BeautifulSoup` 爬取页面内容
- **深度控制**：支持配置爬取深度（默认 1），深度 N 表示从种子 URL 出发跟随 N 层链接
- **磁力链接提取**：从页面中提取所有 `magnet:?xt=urn:btih:...` 链接
- **去重**：读取已有 `magnet.txt` 和 `completed.txt`，避免重复写入
- **追加写入**：将新磁力链接追加写入 `/app/data/magnet.txt`
- **定时调度**：使用 `schedule` 库，按 `CRAWL_INTERVAL` 间隔定时执行
- **环境变量**：
  - `URLS_FILE`：URL 列表文件路径，默认 `/app/data/config/urls.txt`
  - `MAGNET_FILE`：磁力链接输出文件路径，默认 `/app/data/magnet.txt`
  - `COMPLETED_FILE`：已完成记录文件路径，默认 `/app/data/completed.txt`
  - `CRAWL_DEPTH`：爬取深度，默认 `1`
  - `CRAWL_INTERVAL`：调度间隔，默认 `6h`（支持 `1h`、`30m`、`2h` 等格式）

### 3. 创建 `crawler/requirements.txt`

```
requests
beautifulsoup4
schedule
```

### 4. 创建 `crawler/Dockerfile`

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY crawler.py .
CMD ["python", "crawler.py"]
```

### 5. 创建示例 `data/config/urls.txt`

提供示例 URL 列表文件，每行一个种子 URL。

## 验证标准

- [ ] `crawler.py` 可从 `urls.txt` 读取 URL 列表
- [ ] 可爬取页面并提取磁力链接
- [ ] 支持配置爬取深度
- [ ] 去重逻辑正确（不重复写入已有磁力链接）
- [ ] 追加写入 `magnet.txt`，不覆盖已有内容
- [ ] 定时调度正常工作
- [ ] `Dockerfile` 可成功构建
