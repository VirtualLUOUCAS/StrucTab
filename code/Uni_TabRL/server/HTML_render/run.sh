#!/bin/bash
# shellcheck disable=SC1091,SC2140,SC2155
set -e

# 查看本机的进程情况
# ps aux | grep "uvicorn HTML_render:app" | grep -v grep

# 配置
readonly SERVER_NAME="HTML_render"
readonly START_PORT=18940
readonly END_PORT=18969

SHOULD_BUILD_ENV=true  # 是否需要安装依赖
SHOULD_LOAD_FONTS=true # 是否需要复制字体并更新字体缓存
SAVE_LOGS=false        # 是否保存日志文件

readonly FONTS_DIRS=(
    "your/path/to/HTML_render/fonts"
)

readonly PLAYWRIGHT_BROWSERS=(
    "your/path/to/HTML_render/ms-playwright"
)

readonly MATHJAX_DIRS=(
    "your/path/to/HTML_render/mathjax"
)

readonly RENDER_OUTPUT_DIR="your/path/to/render_output"

make_loose_dir() { mkdir -p "$1" && chmod "${2:-777}" "$1"; }

# 获取当前脚本的目录
export SCRIPT_DIR="$(dirname "$(realpath "$0")")"
echo "脚本目录: $SCRIPT_DIR"
cd "${SCRIPT_DIR}"

# 安装依赖
readonly REQUIREMENTS_FILE="${SCRIPT_DIR}/../utils/requirements.txt"
if [ "$SHOULD_BUILD_ENV" = true ]; then
    echo "正在安装依赖..."
    pip install -U pip --root-user-action=ignore
    pip install -r "${REQUIREMENTS_FILE}" --root-user-action=ignore
else
    echo "跳过依赖安装步骤。"
fi

# 查找第一个存在且不为空的目录
find_valid_dir() {
    local dir_name=$1
    shift
    local dirs=("$@")

    for dir in "${dirs[@]}"; do
        if [ -d "$dir" ] && [ -n "$(ls -A "$dir" 2>/dev/null)" ]; then
            echo "$dir"
            return 0
        fi
    done
    echo "错误: 未找到有效的 ${dir_name} 目录" >&2
    exit 1
}

# 查找必需的目录
FONTS_SOURCE_DIR=$(find_valid_dir "字体" "${FONTS_DIRS[@]}")
echo "找到字体目录: $FONTS_SOURCE_DIR"

PLAYWRIGHT_BROWSERS_PATH=$(find_valid_dir "Playwright" "${PLAYWRIGHT_BROWSERS[@]}")
echo "找到 Playwright 浏览器目录: $PLAYWRIGHT_BROWSERS_PATH"
export PLAYWRIGHT_BROWSERS_PATH=${PLAYWRIGHT_BROWSERS_PATH}

MATHJAX_DIR=$(find_valid_dir "MathJax" "${MATHJAX_DIRS[@]}")
echo "找到 MathJax 目录: $MATHJAX_DIR"
export MATHJAX_DIR=${MATHJAX_DIR}

# 复制字体并更新字体缓存
if [ "$SHOULD_LOAD_FONTS" = true ]; then
    echo "正在复制字体并更新字体缓存..."
    mkdir -p /usr/share/fonts/table_render
    chmod 777 /usr/share/fonts/table_render
    cp -n "${FONTS_SOURCE_DIR}"/*.ttc /usr/share/fonts/table_render/ 2>/dev/null || true
    fc-cache -fv
else
    echo "跳过字体复制步骤。"
fi

# 配置日志输出
if [ "$SAVE_LOGS" = true ]; then
    LOGGER_DIR="${SCRIPT_DIR}/../server_logs/${SERVER_NAME}"
    make_loose_dir "${LOGGER_DIR}"
    rm -rf "${LOGGER_DIR:?}"/*
    echo "日志将保存到: ${LOGGER_DIR}"
else
    echo "日志输出已禁用"
fi

make_loose_dir "${RENDER_OUTPUT_DIR}"

# 渲染相关环境变量
export OUT_DIR="${RENDER_OUTPUT_DIR}"
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1

# 在本机启动服务（每个端口一个实例）
echo "正在本机启动 ${SERVER_NAME} 服务..."
for PORT in $(seq "${START_PORT}" "${END_PORT}"); do
    if [ "$SAVE_LOGS" = true ]; then
        LOG_REDIRECT="${LOGGER_DIR}/${PORT}.log"
    else
        LOG_REDIRECT="/dev/null"
    fi
    nohup uvicorn "${SERVER_NAME}:app" --host 0.0.0.0 --port "${PORT}" --workers 1 >"${LOG_REDIRECT}" 2>&1 &
done

echo "所有 ${SERVER_NAME} 服务已在本机启动 (端口 ${START_PORT}-${END_PORT})"
