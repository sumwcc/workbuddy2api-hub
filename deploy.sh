#!/usr/bin/env bash
set -e

# ==============================================================================
# WorkBuddy2API-Hub 一键同步部署到香港服务器脚本 (Local to Hong Kong Runner)
# ==============================================================================

SERVER_IP="34.96.166.42"
SERVER_USER="mwsu"
REMOTE_PATH="/home/mwsu/workbuddy2api-hub"

echo "========================================================"
echo "🚀 准备同步 WorkBuddy2API-Hub 到香港服务器 [${SERVER_USER}@${SERVER_IP}]"
echo "========================================================"

# 1. 增量安全同步源码（严格排除核心账号、配置与统计数据）
echo "📤 增量同步源码到服务器..."
rsync -avz \
  --exclude '.git/' \
  --exclude 'accounts/*.json' \
  --exclude 'accounts/settings.json' \
  --exclude 'accounts/active_realm.json' \
  --exclude 'accounts/model.json' \
  --exclude 'accounts/agent-backups/' \
  --exclude 'usage/' \
  --exclude 'logs/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '*.bak*' \
  --exclude '.vscode/' \
  --exclude '.DS_Store' \
  ./ ${SERVER_USER}@${SERVER_IP}:${REMOTE_PATH}/

# 2. 通过 SSH 平滑热重启 PM2 托管的 wb-proxy 服务
echo "⚡ 连接远程执行 PM2 平滑重载..."
ssh -o StrictHostKeyChecking=no ${SERVER_USER}@${SERVER_IP} "pm2 reload wb-proxy && pm2 status wb-proxy"

echo "========================================================"
echo "✅ 部署已成功完成！Hub 网关已更新并平滑重载！"
echo "========================================================"
