#!/bin/bash
# shellcheck disable=SC1091,SC2140,SC2155
set -e

# 查看本机的进程情况
# ps aux | grep "uvicorn TEDS_judger:app" | grep -v grep

# 配置
readonly SERVER_NAME="TEDS_judger"
readonly START_PORT=18910
readonly END_PORT=18939

SHOULD_BUILD=false # 是否需要安装依赖
SAVE_LOGS=false    # 是否保存日志文件

# 获取当前脚本的目录
export SCRIPT_DIR="$(dirname "$(realpath "$0")")"
echo "脚本目录: $SCRIPT_DIR"
cd "${SCRIPT_DIR}"

# 安装依赖
readonly REQUIREMENTS_FILE="${SCRIPT_DIR}/../utils/requirements.txt"
if [ "$SHOULD_BUILD" = true ]; then
    echo "正在安装依赖..."
    pip install -U pip --root-user-action=ignore
    pip install -r "${REQUIREMENTS_FILE}" --root-user-action=ignore
else
    echo "跳过依赖安装步骤。"
fi

# 配置日志输出
if [ "$SAVE_LOGS" = true ]; then
    LOGGER_DIR="${SCRIPT_DIR}/../server_logs/${SERVER_NAME}"
    mkdir -p "${LOGGER_DIR}"
    rm -rf "${LOGGER_DIR:?}"/*
    echo "日志将保存到: ${LOGGER_DIR}"
else
    echo "日志输出已禁用"
fi

# 在本机启动服务（每个端口一个实例）
for PORT in $(seq "${START_PORT}" "${END_PORT}"); do
    if [ "$SAVE_LOGS" = true ]; then
        LOG_REDIRECT="${LOGGER_DIR}/${PORT}.log"
    else
        LOG_REDIRECT="/dev/null"
    fi
    nohup uvicorn "${SERVER_NAME}:app" --host 0.0.0.0 --port "${PORT}" --workers 1 >"${LOG_REDIRECT}" 2>&1 &
done

echo "所有 ${SERVER_NAME} 服务已在本机启动 (端口 ${START_PORT}-${END_PORT})"
