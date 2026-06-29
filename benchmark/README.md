# StrucTab Benchmark — TableVerse-5K <!-- omit in toc -->

A self-contained inference and evaluation harness for the **TableVerse-5K**
table-parsing benchmark, scored with the structure-aware **TEDS / TEDS-S** metrics.

This is part of the [StrucTab](../README.md) project. A Chinese version of this
document is available in [`README_zh.md`](./README_zh.md).

The pipeline has two stages, **inference → judging**, with pluggable API backends
(`openai_compat` / `local_vllm`). Both stages support **resume** by keying every sample
on its `image_path`.

## Contents <!-- omit in toc -->

- [1. Setup](#1-setup)
- [2. Download benchmark data](#2-download-benchmark-data)
- [3. Inference](#3-inference)
- [4. Judging](#4-judging)
- [5. End-to-end example](#5-end-to-end-example)

## 1. Setup

```bash
cd benchmark
pip install -r requirements.txt
# Optional: only if you plan to use --api_type local_vllm
pip install vllm
```

## 2. Download benchmark data

The **TableVerse-5K** dataset (the `TableVerse_5K.jsonl` annotations plus the `images/`
folder) is hosted as a standalone dataset repository. Clone it and place the contents
under `benchmark/data/` so that the layout becomes:

```
benchmark/data/
├── TableVerse_5K.jsonl
└── images/
    └── *.jpg
```

```bash
# From HuggingFace
git clone https://huggingface.co/datasets/psp-dada/TableVerse-5K
# or from ModelScope
git clone https://www.modelscope.cn/datasets/pspdada/TableVerse-5K.git

# then move TableVerse_5K.jsonl and images/ into benchmark/data/
```

Each line of `TableVerse_5K.jsonl` is a JSON object:

```json
{
  "image_path": "images/xxx.jpg",
  "question": "You are an AI specialized in recognizing and extracting table from images...",
  "ref_answer": "<table>...</table>"
}
```

| Field        | Type   | Description                                                       |
| ------------ | ------ | ----------------------------------------------------------------- |
| `image_path` | string | Relative path from `data/`; also serves as the unique sample key  |
| `question`   | string | The instruction / prompt fed to the model together with the image |
| `ref_answer` | string | Ground-truth table in HTML (`<table>...</table>`)                 |

## 3. Inference

Two backends are supported via `--api_type`: `openai_compat` for any OpenAI-compatible
HTTP service (local or cloud), and `local_vllm` for in-process model loading. Re-running
the same command skips already-completed samples.

```bash
# (a) openai_compat — any OpenAI-compatible HTTP service
#     works with vllm serve / sglang / lmdeploy, or public APIs (OpenAI, Gemini, ...)
python infer.py \
    --api_type openai_compat \
    --model_name Qwen2.5-VL-7B-Instruct \
    --base_url http://127.0.0.1:8000/v1 \
    --api_key EMPTY \
    --max_workers 64

# (b) local_vllm — in-process vLLM, give it a local checkpoint path
python infer.py \
    --api_type local_vllm \
    --model_path /path/to/Qwen2.5-VL-7B-Instruct \
    --tensor_parallel_size 4
```

Each run writes one jsonl, where `<model_tag>` defaults to `--model_name` / the basename
of `--model_path` (override with `--output_tag`):

```
infer_results/<model_tag>/results.jsonl
```

## 4. Judging

Scoring uses the structure-aware **TEDS / TEDS-S** metrics, computed by a standalone
HTTP service rather than in-process. Start the **TEDS judging service** shipped with the
training code, then point the benchmark at it:

```bash
# 1. Start the TEDS service (launches a pool of uvicorn workers exposing /judge/simple)
cd ../code/Uni_TabRL/server/TEDS_judger
bash run.sh
#    → the service listens on ports 18910–18939 of the host by default

# 2. List the resulting host:port endpoints in benchmark/judger_server.json
cat > ../../../../benchmark/judger_server.json <<'EOF'
[
    "127.0.0.1:18910",
    "127.0.0.1:18911"
]
EOF

# 3. Run judging
cd ../../../../benchmark
python judge.py                       # score all models under infer_results/
python judge.py --models Qwen2.5-VL-7B-Instruct   # score specific models only
```

The judge client load-balances requests across all listed endpoints. Outputs:

```
judge_results/<model_tag>/results.jsonl   # per-sample {teds, teds_s, error}
judge_results/<model_tag>/final_rst.json  # per-model averages
judge_results/evaluation_results.xlsx     # aggregated leaderboard (TEDS / TEDS-S)
```

## 5. End-to-end example

```bash
cd benchmark

# 1. Inference
python infer.py --api_type openai_compat \
    --model_name Qwen2.5-VL-7B-Instruct --base_url http://127.0.0.1:8000/v1

# 2. Start the TEDS service and fill judger_server.json (see step 4 above)

# 3. Score
python judge.py
```
