# 任务5：端到端测试与文档更新

## 目标

对整个 SuperMedia 系统进行端到端测试，验证各组件协同工作，并更新项目文档。

## 对话上下文

- 项目：SuperMedia — 自动爬取磁力链接并下载，构建 Jellyfin 媒体仓库
- 设计文档：`docs/superpowers/specs/2026-05-20-docker-compose-orchestration-design.md`
- 前置任务：任务1-4 全部完成
- 关键验证点：
  - 爬虫 → magnet.txt → 下载器 → /media → Jellyfin 完整数据流
  - Docker Compose 一键部署
  - 环境变量配置生效
  - 服务重启自动恢复

## 实现步骤

### 1. 端到端测试

测试流程：
1. `docker compose up -d` 启动所有服务
2. 在 `data/config/urls.txt` 中添加测试 URL
3. 等待爬虫执行，检查 `data/magnet.txt` 是否有新磁力链接
4. 等待下载器执行，检查 `media/` 目录是否有下载文件
5. 检查 `data/completed.txt` 是否记录完成
6. 访问 Jellyfin Web UI，确认媒体库可扫描到新文件
7. `docker compose restart` 重启所有服务，确认自动恢复

### 2. 更新 `readme.md`

- 更新项目状态（所有组件标记为 ✅）
- 更新快速开始部分，添加 Docker Compose 部署命令
- 更新项目结构，反映最终目录布局
- 添加环境变量配置说明

### 3. 更新 `CLAUDE.md`

- 更新架构描述，反映三容器编排
- 更新命令列表，添加 Docker Compose 命令
- 更新配置说明

### 4. 创建 `.gitignore`

排除运行时生成的文件：
- `data/magnet.txt`
- `data/completed.txt`
- `media/`
- `.env`（含敏感配置）

## 验证标准

- [ ] 完整数据流正常工作
- [ ] Docker Compose 一键部署成功
- [ ] 服务重启后自动恢复
- [ ] README 和 CLAUDE.md 已更新
- [ ] `.gitignore` 已创建
