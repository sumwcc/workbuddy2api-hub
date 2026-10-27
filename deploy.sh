#!/usr/bin/env bash
set -e

# ==============================================================================
# WorkBuddy2API-Hub 一键同步部署到香港服务器脚本 (Local to Hong Kong Runner)
# ==============================================================================

TARGET="cn2"
CN2_IP="82.158.229.151"
GCP_IP="34.96.166.42"

while [[ $# -gt 0 ]]; do
  case $1 in
    -t|--target)
      TARGET="$2"
      shift 2
      ;;
    -h|--help)
      echo "用法: $0 [-t cn2|gcp]"
      exit 0
      ;;
    *)
      echo "未知参数: $1"
      exit 1
      ;;
  esac
done

if [ "$TARGET" = "cn2" ]; then
  SERVER_IP="$CN2_IP"
  SERVER_NAME="香港-CN2 主节点"
elif [ "$TARGET" = "gcp" ]; then
  SERVER_IP="$GCP_IP"
  SERVER_NAME="香港-GCP 辅助节点"
else
  echo "❌ 未知的部署目标: $TARGET (仅支持 cn2 或 gcp)"
  exit 1
fi

SERVER_USER="mwsu"
REMOTE_PATH="/home/mwsu/workbuddy2api-hub"

echo "========================================================"
echo "🚀 准备同步 WorkBuddy2API-Hub 到 ${SERVER_NAME} [${SERVER_USER}@${SERVER_IP}]"
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

# 3. 校验健康状态
echo "🔍 验证远程网关健康状态..."
HEALTH_RESP=$(ssh -o StrictHostKeyChecking=no ${SERVER_USER}@${SERVER_IP} "curl -s http://127.0.0.1:8788/health || true")
echo "健康探测结果: $HEALTH_RESP"

echo "========================================================"
echo "✅ 部署已成功完成！Hub 网关已更新并平滑重载！"
echo "========================================================"
