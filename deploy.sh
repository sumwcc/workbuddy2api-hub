#!/usr/bin/env bash
# ==============================================================================
# workbuddy2api-hub 一键发布入口（本地 -> 香港服务器，PM2 蓝绿零停机）
# ==============================================================================
# 本脚本只是薄封装，真正的发布流程在同级的 new-api-cf 仓库里：
#   new-api-cf/scripts/local_deploy_hub.sh                  本地：rsync 源码 + 触发远端切换
#   new-api-cf/scripts/server_hub_blue_green_deploy.sh       服务器端：蓝绿热切换执行器
#
# 发布方式为 Nginx 反代 + PM2 双槽位蓝绿热切换：
#   入口：127.0.0.1:8788（Nginx，upstream 见 /etc/nginx/snippets/upstream_hub.conf）
#   槽位：wb-proxy-blue :8791 / wb-proxy-green :8792
#   流程：拉起对端槽位 -> /health 探针 -> Nginx 瞬时切流 -> 旧槽 300s 长连接护航退出
#
# 用法:
#   ./deploy.sh                      # 默认发 cn2 (82.158.229.151)
#   ./deploy.sh -t node2             # 发 Node 2 (45.207.212.73)
#   ./deploy.sh -t 1.2.3.4           # 发任意 IP
#   NEW_API_CF_DIR=/path/to/new-api-cf ./deploy.sh -t cn2   # 自定义 new-api-cf 位置
# ==============================================================================

set -euo pipefail

CN2_IP="82.158.229.151"
NODE2_IP="45.207.212.73"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NEW_API_CF_DIR="${NEW_API_CF_DIR:-${SCRIPT_DIR}/../new-api-cf}"

TARGET="cn2"

usage() {
  echo "用法: $0 [-t cn2|node2|<IP>]"
  echo "  cn2    香港-CN2 Node 1  ${CN2_IP}"
  echo "  node2  香港-CN2 Node 2  ${NODE2_IP}"
  echo "  <IP>   任意自定义目标 IP"
  echo "  （不传 -t 时默认 cn2）"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -t|--target)
      TARGET="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "❌ 未知参数: $1"
      usage
      exit 1
      ;;
  esac
done

if [ -z "$TARGET" ]; then
  echo "❌ -t/--target 需要一个值"
  usage
  exit 1
fi

case "$TARGET" in
  cn2)
    SERVER_IP="$CN2_IP"
    SERVER_NAME="香港-CN2 Node 1"
    ;;
  node2)
    SERVER_IP="$NODE2_IP"
    SERVER_NAME="香港-CN2 Node 2"
    ;;
  *)
    SERVER_IP="$TARGET"
    SERVER_NAME="自定义目标"
    ;;
esac

DEPLOY_SCRIPT="${NEW_API_CF_DIR}/scripts/local_deploy_hub.sh"
if [ ! -f "$DEPLOY_SCRIPT" ]; then
  echo "❌ 未找到发布脚本: ${DEPLOY_SCRIPT}"
  echo "   请确认 new-api-cf 与本仓库同级，或用 NEW_API_CF_DIR 指定其路径。"
  exit 1
fi

echo "========================================================"
echo "🚀 准备按蓝绿流程发布号池 (wb-proxy) 到 ${SERVER_NAME} [mwsu@${SERVER_IP}]"
echo "   远端流程: ${DEPLOY_SCRIPT} --ip ${SERVER_IP}"
echo "========================================================"

exec bash "$DEPLOY_SCRIPT" --ip "$SERVER_IP"
