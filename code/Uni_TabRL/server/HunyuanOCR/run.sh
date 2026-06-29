#!/bin/bash
set -e

# ======================
# 配置
# ======================
readonly START_GPU=0
readonly END_GPU=7
readonly START_PORT=8021
readonly SERVER_NAME="vllm_hunyuan_ocr"

# 模型路径优先级列表
readonly MODEL_PATHS=(
    "your/path/to/HunyuanOCR"
)

readonly DRAFT_MODEL_PATHS=(
    "your/path/to/HunyuanOCR-eagle3"
)

# 获取当前脚本的目录
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
LOG_DIR="${SCRIPT_DIR}/../server_logs/${SERVER_NAME}"

# ======================
# 工具函数
# ======================
make_loose_dir() {
    mkdir -p "$1" && chmod "${2:-777}" "$1"
}

# 查找第一个存在的目录
find_valid_dir() {
    local dir_name=$1
    shift
    local dirs=("$@")

    for dir in "${dirs[@]}"; do
        if [ -d "$dir" ]; then
            echo "$dir"
            return 0
        fi
    done
    echo "错误: 未找到有效的 ${dir_name} 目录" >&2
    exit 1
}

# ======================
# 查找模型路径
# ======================
echo "正在查找模型路径..."
model_path=$(find_valid_dir "主模型" "${MODEL_PATHS[@]}")
echo "找到主模型路径: $model_path"

draft_model_path=$(find_valid_dir "Draft模型" "${DRAFT_MODEL_PATHS[@]}")
echo "找到Draft模型路径: $draft_model_path"

speculative_config='{"method":"eagle3","model":"'"${draft_model_path}"'","num_speculative_tokens":4}'

# ======================
# 创建日志目录
# ======================
echo "日志将保存到: ${LOG_DIR}"
make_loose_dir "${LOG_DIR}"
rm -rf "${LOG_DIR:?}"/*

# ======================
# 启动多个 vLLM 实例
# ======================
echo "正在启动 vLLM 服务..."

for GPU_IDX in $(seq ${START_GPU} ${END_GPU}); do
    PORT=$((START_PORT + GPU_IDX - START_GPU))
    LOG_FILE="${LOG_DIR}/gpu${GPU_IDX}_port${PORT}.log"

    echo "[INFO] 启动实例 - GPU: ${GPU_IDX}, PORT: ${PORT}"

    # 使用 nohup 在后台启动
    CUDA_VISIBLE_DEVICES="${GPU_IDX}" nohup vllm serve \
        "${model_path}" \
        --served-model-name HYVL \
        -tp 1 \
        --limit-mm-per-prompt '{"image":4,"video":0}' \
        --trust_remote_code \
        --port "${PORT}" \
        --gpu-memory-utilization 0.8 \
        --speculative-config "${speculative_config}" \
        --load-format 'runai_streamer' \
        --model-loader-extra-config '{"concurrency":16}' \
        >"${LOG_FILE}" 2>&1 &

    sleep 0.5
done

echo "所有 vLLM 服务已启动完成"
echo "GPU 范围: ${START_GPU} - ${END_GPU}"
echo "Port 范围: ${START_PORT} - $((START_PORT + END_GPU - START_GPU))"
echo "日志目录: ${LOG_DIR}"
