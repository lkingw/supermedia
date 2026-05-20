# 任务4：集成 Jellyfin 服务

## 目标

配置 Jellyfin 容器，使其能正确扫描下载器输出的媒体文件并提供播放服务。

## 对话上下文

- 项目：SuperMedia — 自动爬取磁力链接并下载，构建 Jellyfin 媒体仓库
- 设计文档：`docs/superpowers/specs/2026-05-20-docker-compose-orchestration-design.md`
- 关键决策：
  - Jellyfin 使用官方镜像 `jellyfin/jellyfin:latest`
  - 挂载 `./media` 为只读
  - bridge 网络 + 端口映射 8096
  - 配置和缓存使用 Docker named volumes
  - 重启策略：`unless-stopped`

## 实现步骤

### 1. 优化 Jellyfin 卷挂载

在 `docker-compose.yml` 中确保：
- `/media` 挂载为只读（`:ro`），Jellyfin 只读取不写入
- `/config` 使用 named volume 持久化 Jellyfin 配置
- `/cache` 使用 named volume 持久化 Jellyfin 缓存

### 2. 媒体目录结构规范

在 `/media` 下创建标准媒体库目录结构，方便 Jellyfin 识别：

```
/media/
├── movies/     # 电影
├── tv/         # 电视剧
└── music/      # 音乐
```

> 注意：aria2c 下载的文件目录结构由种子内容决定，可能需要后续手动整理或通过脚本自动分类。此任务仅创建基础目录结构。

### 3. Jellyfin 初始化配置

- 首次启动后通过 Web UI 完成初始化设置
- 添加媒体库：分别添加 movies、tv、music 三个媒体库
- 配置元数据语言为中文

### 4. 自动扫描触发

Jellyfin 默认会定时扫描媒体库，无需额外配置。如需更及时的扫描，可考虑：
- 在下载完成后通过 Jellyfin API 触发扫描（后续优化，不在本任务范围）

## 验证标准

- [ ] Jellyfin 容器正常启动
- [ ] 可通过 `http://<host>:8096` 访问 Web UI
- [ ] 媒体库目录结构正确
- [ ] 配置和缓存持久化（容器重启后不丢失）
- [ ] 可正常扫描和播放媒体文件
