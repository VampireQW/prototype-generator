#!/bin/sh
# Fly.io 启动脚本
# Volume 挂载到 /data，将需要持久化的目录链接过去

PERSISTENT_DIR="/data"

# 创建持久目录
for dir in data projects deleted uploads backups; do
    mkdir -p "$PERSISTENT_DIR/$dir"
done

# 删除应用目录中的原始文件夹（如果存在），建立软链接
for dir in data projects deleted uploads backups; do
    rm -rf "/app/$dir"
    ln -sf "$PERSISTENT_DIR/$dir" "/app/$dir"
done

echo "[Fly.io] 持久化目录已链接"

# 启动服务
cd /app
exec python server.py
