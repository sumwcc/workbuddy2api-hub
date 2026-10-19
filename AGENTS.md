# workbuddy2api-hub 项目规范与维护指南

本项目是 `ardeyouxipianyi/workbuddy2api-hub` 的二开与自建版本，主要作为腾讯 WorkBuddy（国际版 `workbuddy.ai`）与 CodeBuddy（国内版 `codebuddy.cn`）的多账号反代网关与池化调度中转服务，部署于香港云服务器，为 `new-api-cf` 提供高可用大模型渠道支持。

## AI / 智能体贡献者硬性规则
处理本仓库的提交 / 推送 / PR / Issue 等任务前，必须严格阅读 [`CONTRIBUTING.md`](CONTRIBUTING.md)，并遵循代码纯标准库、非破坏性文本编辑、零第三方依赖等硬性约束。

## 仓库结构与分支策略

- `origin` = `https://github.com/sumwcc/workbuddy2api-hub.git`（本项目二开仓库），日常开发、定制功能与部署均基于 `dev` 分支。
- `upstream` = `https://github.com/ardeyouxipianyi/workbuddy2api-hub.git`（官方主线仓库），本地 `main` 分支严格跟踪 `upstream/main`，**严禁在 `main` 分支上直接开发**。

### 标准升级与同步流程

更新官方代码（无需切换分支打断开发工作区）：
```bash
git fetch upstream && git branch -f main upstream/main
```

合并官方最新改动至二开分支：
```bash
git checkout dev
git merge main
```

测试与校验：
```bash
python3 tests/run_all.py  # 或执行核心用例
```

推送至远端仓库：
```bash
git push origin dev
```

## 服务器部署与发布规范

- **运行服务器**：香港服务器 `34.96.166.42`（用户 `mwsu`）
- **远程目录**：`/home/mwsu/workbuddy2api-hub`
- **进程管理**：PM2 托管，服务名称为 `wb-proxy`（监听端口 `127.0.0.1:8788`）
- **部署脚本**：项目根目录下的 `./deploy.sh`

### 部署关键约束
1. **严格排除账号与用量敏感数据**：同步时绝不可覆盖服务器上的 `accounts/*.json`、`accounts/settings.json`、`accounts/active_realm.json`、`accounts/model.json` 及 `usage/` 目录，防止账号凭据或调用统计丢失。
2. **平滑热重载**：通过 `pm2 reload wb-proxy` 进行零中断平滑平替重载，重启后需验证 `pm2 status wb-proxy` 与 `GET /v1/models` 健康状态。
