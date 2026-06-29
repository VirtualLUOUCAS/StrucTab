#!/bin/bash
# shellcheck disable=SC1091,SC2155

SERVER_NAME="TEDS_judger"

# 停止本机上的服务
echo "正在停止本机上的 ${SERVER_NAME} 服务..."
pkill -f "uvicorn.*${SERVER_NAME}:app" || true
echo "${SERVER_NAME} 服务已停止"
