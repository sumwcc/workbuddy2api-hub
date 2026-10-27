// ==============================================================================
// workbuddy2api-hub 号池服务 PM2 生产启动配置文件
// 部署位置：/home/mwsu/workbuddy2api-hub/ecosystem.config.js
// 启动命令：pm2 start ecosystem.config.js
// ==============================================================================

module.exports = {
  apps: [
    {
      name: 'wb-proxy',
      cwd: '/home/mwsu/workbuddy2api-hub',
      script: 'wb_proxy.py',
      interpreter: 'python3',
      args: '--host 127.0.0.1 --port 8788',
      env: {
        WB_MAX_CONCURRENT_CHAT: '128',
        WB_CHAT_SLOT_WAIT: '60',
        WB_UPSTREAM_POOL_SIZE: '32',
        WB_DESKTOP_CHAT_COMPAT: '1',
        PYTHONUNBUFFERED: '1',
      },
      restart_delay: 3000,
      max_restarts: 10,
      autorestart: true,
    },
  ],
};
