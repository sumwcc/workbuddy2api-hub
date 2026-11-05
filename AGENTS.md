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

### 现役服务器（两台）

| 节点 | IP | 用户 | 远程目录 |
|---|---|---|---|
| Node 1（香港-CN2 主节点） | `82.158.229.151` | `mwsu` | `/home/mwsu/workbuddy2api-hub` |
| Node 2（香港-CN2 从节点） | `45.207.212.73` | `mwsu` | `/home/mwsu/workbuddy2api-hub` |

### 发布架构：PM2 蓝绿双槽位 + Nginx 切流（零停机）

- **Nginx 入口**：`127.0.0.1:8788`，upstream 文件 `/etc/nginx/snippets/upstream_hub.conf`（站配置 `/etc/nginx/conf.d/hub_upstream.conf`）；
- **PM2 双槽位**：`wb-proxy-blue` 监听 `127.0.0.1:8791`，`wb-proxy-green` 监听 `127.0.0.1:8792`，启动参数 `python3 wb_proxy.py --host 127.0.0.1 --port <PORT>`；
- **发布流程**（`new-api-cf/scripts/server_hub_blue_green_deploy.sh`）：自动判定活跃槽位 → 拉起对端槽位 → `/health` 15s 自旋探针 → Nginx 热切流（0.1s 生效）→ 旧槽 300s 长连接护航后退出；探针失败则回滚，旧槽流量不受影响；
- **注意**：不存在名为 `wb-proxy` 的 PM2 进程，`pm2 reload wb-proxy` 一定失败，排障请用槽位名（`pm2 logs wb-proxy-blue` / `wb-proxy-green`）。

### 发布命令

项目根目录的 `./deploy.sh` 是薄封装，内部委托 `new-api-cf/scripts/local_deploy_hub.sh`（可用 `NEW_API_CF_DIR` 指定该仓路径）：

```bash
./deploy.sh -t cn2        # 发布 Node 1（默认，等价于不带 -t）
./deploy.sh -t node2      # 发布 Node 2
./deploy.sh -t <IP>       # 任意目标
```

`-t` 只认 `cn2` / `node2` / 字面 IP。等价底层命令：`bash ../new-api-cf/scripts/local_deploy_hub.sh --ip 82.158.229.151`。

### 部署关键约束
1. **严格排除账号与用量敏感数据**：同步时绝不可覆盖服务器上的 `accounts/`（含 `accounts/*.json`、`accounts/settings.json`、`accounts/active_realm.json`、`accounts/model.json`、`accounts/codearts/`、`accounts/agent-backups/`）、`usage/`、`logs/`，防止账号凭据或调用统计丢失。
2. **以健康探针为准，不要手工 `pm2 restart`**：蓝绿切流已保证零中断，手工重启会打断正在进行的大模型流式长连接；发布后校验 `GET http://127.0.0.1:8788/health`（200）与一次真实 `POST /v1/chat/completions`（200）。
3. **发布失败的回滚**：故障发生在切流前 → 旧槽未受影响，直接重试；切流后发现问题 → 对同一台再发一次（会自动切回对端槽位），或手动把 `/etc/nginx/snippets/upstream_hub.conf` 改回旧端口并 `sudo nginx -s reload`。
4. **巡检守护**：服务器上 `cron_rotate_hub.sh` 每 15 分钟检查活跃槽位 RSS 与宿主机可用内存，超限或每日 04:30 触发一次无感轮转，勿手动删除该 crontab。
