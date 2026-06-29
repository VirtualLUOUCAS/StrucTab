# StrucTab: A Structured Optimization Framework for Table Parsing

This repository contains the code release for **StrucTab**. It is organized into
three parts that mirror the paper: training-data construction, the Uni-TabRL
reward, and the analysis scripts behind the figures and tables.

> A Chinese version of this document is available in [`README_zh.md`](./README_zh.md).

## Repository layout

```
Release/
├── training_data/
│   └── get_sequencial_reasoning.py   # Sec. A.1 + Algorithm 1: build sequential-reasoning data from HTML
├── Uni_TabRL/
│   ├── configs/servers/                        # endpoint lists (host:port) for the four reward services
│   ├── reward/                                 # the decomposed RL reward
│   └── server/                                 # the four dependency services
└── analysis/
    ├── get_benchmark_statics.py                # Table 1: benchmark statistics
    ├── get_benchmark_with_cue.py               # Fig. 4(a): build the "with cue" prompts
    └── structure_probe_experiment.ipynb        # Fig. 4(b): early-error-correction probe
```

## 1. Training data — `training_data/`

`get_sequencial_reasoning.py` implements the structural decomposition
and annotation pipeline described in **Sec. A.1** and **Algorithm 1**. Given raw
`(image, HTML)` pairs, it derives, for each table:

- the **row/column counts**,
- the **merged-cell** description (via a virtual-grid sweep that emits
  `<merge>(r1,c1),(r2,c2)</merge>` tokens),
- a **sequential-reasoning target** that chains the three subtasks in the order
  _row-column counting → merged-cell analysis → final HTML parsing_.

Set `INPUT_FILES` to your `.jsonl` files and run the script; results are written
to `*_processed.jsonl`.

## 2. Uni-TabRL reward — `Uni_TabRL/reward/`

The reward follows the decomposed formulation in the paper:

```
R = λ1 · R_validity + λ2 · R_structure + λ3 · R_content
```

with the paper's weights `λ1 = 0.4, λ2 = 0.3, λ3 = 0.3`. The entry point is
`reward_func.compute_reward`. If a response is not even syntactically parsable
(missing section markers or an unterminated final table), the whole reward is 0.

```
reward/
├── config.py              # weights + ablation switches
├── reward_func.py         # entry point: compute_reward
├── validity/              # R_validity: binary hard gating (row-col AND merged-cell exact)
├── structure/             # R_structure: teds_s | 1d_probe
├── content/               # R_content: teds | vlm_judge | anchor
└── utils/                 # parsing, clients, server registry, image IO
```

Each reward part is a package exposing its interface function, with helper code
kept in a sibling `utils.py`:

- **validity** — `validity_reward()`: returns 1 only when both the row-column
  counting and the merged-cell analysis exactly match the reference.
- **structure** — `one_d_probe_reward()`: the 1D Probe reward, i.e. the fraction
  of cells matched before the first structural mismatch in row-major order.
- **content** — `teds_content_reward()`, `vlm_judge_content_reward()`,
  `anchor_destylization_content_reward()`.

### Reproducing the ablations (Table "Effectiveness of Uni-TabRL")

Two environment variables select the structure / content variant:

| `STRUCTURE_REWARD` | `CONTENT_REWARD` | Paper setting                     |
| ------------------ | ---------------- | --------------------------------- |
| `teds_s`           | `teds`           | (a) RL baseline                   |
| `teds_s`           | `vlm_judge`      | (b) + VLM judge                   |
| `teds_s`           | `anchor`         | (c) + Anchor-Guided Destylization |
| `1d_probe`         | `teds`           | (d) + 1D Probe                    |
| `1d_probe`         | `anchor`         | (e) StrucTab (final)              |

```bash
export STRUCTURE_REWARD=1d_probe
export CONTENT_REWARD=anchor
# optional: override weights
export VALIDITY_WEIGHT=0.4 STRUCTURE_WEIGHT=0.3 CONTENT_WEIGHT=0.3
```

The `vlm_judge` and `anchor` content variants are applied only on the training
split; on the test split the reward falls back to raw TEDS.

## 3. Reward dependency services — `Uni_TabRL/server/`

The content/structure rewards depend on four services. Each runs as a standalone
HTTP/OpenAI-compatible service, and the reward clients discover them by reading
an endpoint list (a list of `"host:port"` strings) from `configs/servers/`:

| Service       | Role                                | Config file                        |
| ------------- | ----------------------------------- | ---------------------------------- |
| `HunyuanOCR`  | Anchor OCR model (vLLM)             | `configs/servers/hunyuan_ocr.json` |
| `HTML_render` | HTML-to-image renderer (Playwright) | `configs/servers/html_render.json` |
| `TEDS_judger` | TEDS / TEDS-S scoring (FastAPI)     | `configs/servers/teds_judger.json` |
| `vlm_judge`   | VLM-as-judge consistency (vLLM)     | `configs/servers/vlm_judge.json`   |

Launch each service with its `run.sh` (fill in your own asset/model paths at the
top of the script), then list the resulting `host:port` endpoints in the
corresponding JSON file. Each service folder also ships a `ping_*.py` health
check. The OpenAI-compatible clients resolve the served model name automatically,
so no model name needs to be configured.

Before running the reward, set the render output location:

```bash
export OUTPUT_PATH=/your/output/root
export PROJECT_NAME=structab
export EXPERIMENT_NAME=uni_tabrl
```

## 4. Analysis — `analysis/`

- **`get_benchmark_statics.py`** — computes the benchmark statistics in
  **Table 1** (size, average rows/columns, average merged-cell count).
- **`get_benchmark_with_cue.py`** — builds the four prompt variants
  (`direct`, `with_size`, `with_merge`, `with_both`) for the
  _Impact of explicit structural cues_ study in **Fig. 4(a)**.
- **`structure_probe_experiment.ipynb`** — the structural probe for
  _Impact of early error correction_ in **Fig. 4(b)**: it locates the first
  structural error in a generation, corrects it, re-runs the model, and compares
  the subsequent error rate and generation confidence (logp).

Fill in your own data paths (placeholders are written as `your/path/to/...`)
before running any script.

## Environment

```bash
pip install -r Uni_TabRL/server/utils/requirements.txt
```
