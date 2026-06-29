# StrucTab 基准 —— TableVerse-5K <!-- omit in toc -->

面向 **TableVerse-5K** 表格解析基准的自包含推理与评测框架，使用结构感知的
**TEDS / TEDS-S** 指标评分。

本目录是 [StrucTab](../README_zh.md) 项目的一部分。English version of this document is
available in [`README.md`](./README.md)。

整个流程分为 **推理 → 评测** 两个阶段，支持可插拔的 API 后端（`openai_compat` /
`local_vllm`）。两个阶段都以样本的 `image_path` 为主键，支持**断点续跑**。

## 目录 <!-- omit in toc -->

- [1. 环境准备](#1-环境准备)
- [2. 下载基准数据](#2-下载基准数据)
- [3. 推理](#3-推理)
- [4. 评测](#4-评测)
- [5. 端到端示例](#5-端到端示例)

## 1. 环境准备

```bash
cd benchmark
pip install -r requirements.txt
# 可选：仅当你打算使用 --api_type local_vllm 时安装
pip install vllm
```

## 2. 下载基准数据

**TableVerse-5K** 数据集（`TableVerse_5K.jsonl` 标注文件加上 `images/` 文件夹）作为独立的
数据集仓库托管。请克隆它并将内容放入 `benchmark/data/`，使目录结构为：

```
benchmark/data/
├── TableVerse_5K.jsonl
└── images/
    └── *.jpg
```

```bash
# 从 HuggingFace
git clone https://huggingface.co/datasets/psp-dada/TableVerse-5K
# 或从 ModelScope
git clone https://www.modelscope.cn/datasets/pspdada/TableVerse-5K.git

# 随后将 TableVerse_5K.jsonl 与 images/ 移动到 benchmark/data/ 下
```

`TableVerse_5K.jsonl` 每一行为一个 JSON 对象：

```json
{
  "image_path": "images/xxx.jpg",
  "question": "You are an AI specialized in recognizing and extracting table from images...",
  "ref_answer": "<table>...</table>"
}
```

| 字段         | 类型   | 说明                                              |
| ------------ | ------ | ------------------------------------------------- |
| `image_path` | string | 相对于 `data/` 的图片路径，同时作为样本的唯一主键 |
| `question`   | string | 与图像一同送入模型的指令 / 提示词                 |
| `ref_answer` | string | HTML 格式的标准答案表格（`<table>...</table>`）   |

## 3. 推理

通过 `--api_type` 支持两种后端：`openai_compat` 适用于任意 OpenAI 兼容的 HTTP 服务（本地
或云端），`local_vllm` 适用于进程内加载模型。重复运行同一条命令会自动跳过已完成的样本。

```bash
# (a) openai_compat —— 任意 OpenAI 兼容的 HTTP 服务
#     适用于 vllm serve / sglang / lmdeploy，或公有云 API（OpenAI、Gemini 等）
python infer.py \
    --api_type openai_compat \
    --model_name Qwen2.5-VL-7B-Instruct \
    --base_url http://127.0.0.1:8000/v1 \
    --api_key EMPTY \
    --max_workers 64

# (b) local_vllm —— 进程内 vLLM，传入本地权重路径
python infer.py \
    --api_type local_vllm \
    --model_path /path/to/Qwen2.5-VL-7B-Instruct \
    --tensor_parallel_size 4
```

每次运行写出一个 jsonl，其中 `<model_tag>` 默认取 `--model_name` / `--model_path` 的
basename（可用 `--output_tag` 覆盖）：

```
infer_results/<model_tag>/results.jsonl
```

## 4. 评测

评分使用结构感知的 **TEDS / TEDS-S** 指标，由一个独立的 HTTP 服务计算，而非进程内计算。先
启动随训练代码一起发布的 **TEDS 打分服务**，再让基准指向它：

```bash
# 1. 启动 TEDS 服务（拉起一组 uvicorn worker，暴露 /judge/simple）
cd ../code/Uni_TabRL/server/TEDS_judger
bash run.sh
#    → 服务默认监听本机的 18910–18939 端口

# 2. 将得到的 host:port 端点填入 benchmark/judger_server.json
cat > ../../../../benchmark/judger_server.json <<'EOF'
[
    "127.0.0.1:18910",
    "127.0.0.1:18911"
]
EOF

# 3. 运行评测
cd ../../../../benchmark
python judge.py                       # 评测 infer_results/ 下所有模型
python judge.py --models Qwen2.5-VL-7B-Instruct   # 仅评测指定模型
```

评测客户端会在所有列出的端点间做负载均衡。输出：

```
judge_results/<model_tag>/results.jsonl   # 逐样本 {teds, teds_s, error}
judge_results/<model_tag>/final_rst.json  # 各模型平均分
judge_results/evaluation_results.xlsx     # 汇总榜单（TEDS / TEDS-S）
```

## 5. 端到端示例

```bash
cd benchmark

# 1. 推理
python infer.py --api_type openai_compat \
    --model_name Qwen2.5-VL-7B-Instruct --base_url http://127.0.0.1:8000/v1

# 2. 启动 TEDS 服务并填写 judger_server.json（见上面第 4 步）

# 3. 评分
python judge.py
```
