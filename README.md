# StrucTab <!-- omit in toc -->

**A Structured Optimization Framework for Table Parsing**

<p align="center">
  <a href="README_zh.md">中文版</a> •
  <a href="https://github.com/VirtualLUOUCAS/StrucTab">GitHub Repo</a> •
  <a href="https://huggingface.co/datasets/psp-dada/TableVerse-5K">HuggingFace Dataset</a> •
  <a href="https://modelscope.cn/datasets/pspdada/TableVerse-5K">ModelScope Dataset</a> •
  <a>Paper (coming soon)</a>
</p>

## News <!-- omit in toc -->

- [2026.06] 📖 Code and the TableVerse-5K benchmark are released!

## Overview <!-- omit in toc -->

**StrucTab** is a structured optimization framework for **table parsing**, the task of converting a table image into structured HTML. Instead of treating parsing as a flat image-to-text problem, StrucTab decomposes it into three coupled subtasks, namely row/column counting, merged-cell analysis, and final HTML generation, and optimizes a reinforcement-learning reward that is itself decomposed along the same axes (`validity`, `structure`, `content`).

## Contents <!-- omit in toc -->

- [Repository Layout](#repository-layout)
- [Code](#code)
- [Benchmark](#benchmark)
- [Citation](#citation)
- [License](#license)

## Repository Layout

This repository releases:

- **`code/`** — the training-data construction pipeline, the Uni-TabRL reward, its four
  dependency services, and the analysis scripts behind the paper's figures and tables.
- **`benchmark/`** — a self-contained inference and evaluation harness for the
  **TableVerse-5K** table-parsing benchmark, scored with the structure-aware
  TEDS / TEDS-S metrics.

<details>
<summary>Full directory tree (click to expand)</summary>

```
StrucTab/
├── README.md
├── code/                         # training + RL reward + analysis (see code/README.md)
│   ├── training_data/            # build sequential-reasoning data from (image, HTML) pairs
│   ├── Uni_TabRL/
│   │   ├── reward/               # the decomposed RL reward (validity / structure / content)
│   │   ├── server/               # the four reward dependency services
│   │   │   └── TEDS_judger/      # TEDS / TEDS-S scoring service (also used by the benchmark)
│   │   └── configs/servers/      # endpoint lists for the reward services
│   └── analysis/                 # scripts behind the paper figures / tables
└── benchmark/                    # inference + evaluation harness for TableVerse-5K
    ├── apis/                     # pluggable backends: openai_compat | local_vllm
    ├── utils/                    # incremental writer, image encoding, signal handling
    ├── data/                     # ← place the TableVerse-5K dataset here
    ├── infer.py                  # entry: inference  → infer_results/<tag>/results.jsonl
    ├── judge.py                  # entry: TEDS scoring → judge_results/<tag>/results.jsonl
    ├── judger_server.json        # TEDS service endpoint list (host:port)
    └── requirements.txt
```

</details>

## Code

The model-side code (training-data construction, the Uni-TabRL reward, the four
dependency services, and the analysis scripts) is documented separately in
[`code/README.md`](code/README.md) (中文版：[`code/README_zh.md`](code/README_zh.md)).

## Benchmark

`benchmark/` is a self-contained harness for the **TableVerse-5K** table-parsing
benchmark. It runs a two-stage pipeline, **inference → judging**, with pluggable API
backends (`openai_compat` / `local_vllm`) and a structure-aware **TEDS / TEDS-S** scorer.
Both stages support **resume** by keying every sample on its `image_path`.

For full setup, data download, and step-by-step inference / judging instructions, see
[`benchmark/README.md`](benchmark/README.md) (中文版：[`benchmark/README_zh.md`](benchmark/README_zh.md)).

## Citation

If you find StrucTab useful, please consider citing:

```bibtex
TBD
```

## License

This project is released for **research purposes only**.
