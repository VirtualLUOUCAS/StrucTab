# StrucTab：面向表格解析的结构化优化框架

本仓库是 **StrucTab** 的代码开源版本，按论文结构分为三部分：训练数据构造、
Uni-TabRL 奖励，以及生成论文图表所用的分析脚本。

> The English version is available in [`README.md`](./README.md).

## 目录结构

```
Release/
├── training_data/
│   └── get_sequencial_reasoning.py   # A.1 节 + 算法 1：从 HTML 构造序列推理数据
├── Uni_TabRL/
│   ├── configs/servers/                        # 四个奖励依赖服务的端点列表（host:port）
│   ├── reward/                                 # 分解式 RL 奖励
│   └── server/                                 # 四个依赖服务
└── analysis/
    ├── get_benchmark_statics.py                # 表 1：benchmark 统计
    ├── get_benchmark_with_cue.py               # 图 4(a)：构造 “with cue” 提示
    └── structure_probe_experiment.ipynb        # 图 4(b)：早期纠错探针实验
```

## 1. 训练数据 —— `training_data/`

`get_sequencial_reasoning.py` 实现了 **A.1 节** 与 **算法 1** 描述的
结构分解与标注流程。给定原始 `(图像, HTML)` 对，脚本会为每个表格生成：

- **行列数**；
- **合并单元格** 描述（通过虚拟网格扫描，输出
  `<merge>(r1,c1),(r2,c2)</merge>` 形式的 token）；
- **序列推理目标**，按 _行列计数 → 合并单元格分析 → 最终 HTML 解析_ 的顺序
  把三个子任务串联起来。

将 `INPUT_FILES` 设为你的 `.jsonl` 文件后运行脚本，结果写入 `*_processed.jsonl`。

## 2. Uni-TabRL 奖励 —— `Uni_TabRL/reward/`

奖励遵循论文中的分解式定义：

```
R = λ1 · R_validity + λ2 · R_structure + λ3 · R_content
```

权重取论文值 `λ1 = 0.4, λ2 = 0.3, λ3 = 0.3`。入口为
`reward_func.compute_reward`。若响应连语法都无法解析（缺少分段标记，或最终表格
没有正常闭合），整体奖励为 0。

```
reward/
├── config.py              # 权重 + 消融开关
├── reward_func.py         # 入口：compute_reward
├── validity/              # R_validity：二值硬门控（行列数与合并单元格均需完全正确）
├── structure/             # R_structure：teds_s | 1d_probe
├── content/               # R_content：teds | vlm_judge | anchor
└── utils/                 # 解析、客户端、服务注册、图像 IO
```

每个奖励部分都是一个子包，对外暴露其接口函数，辅助代码放在同目录的
`utils.py` 中：

- **validity** —— `validity_reward()`：仅当行列计数与合并单元格分析都与参考
  完全一致时返回 1。
- **structure** —— `one_d_probe_reward()`：1D Probe 奖励，即按行优先顺序，在第一个
  结构不匹配之前匹配成功的单元格占比。
- **content** —— `teds_content_reward()`、`vlm_judge_content_reward()`、
  `anchor_destylization_content_reward()`。

### 复现消融实验（表 “Effectiveness of Uni-TabRL”）

通过两个环境变量选择结构 / 内容奖励的变体：

| `STRUCTURE_REWARD` | `CONTENT_REWARD` | 对应论文设置                      |
| ------------------ | ---------------- | --------------------------------- |
| `teds_s`           | `teds`           | (a) RL baseline                   |
| `teds_s`           | `vlm_judge`      | (b) + VLM judge                   |
| `teds_s`           | `anchor`         | (c) + Anchor-Guided Destylization |
| `1d_probe`         | `teds`           | (d) + 1D Probe                    |
| `1d_probe`         | `anchor`         | (e) StrucTab（最终版）            |

```bash
export STRUCTURE_REWARD=1d_probe
export CONTENT_REWARD=anchor
# 可选：覆盖权重
export VALIDITY_WEIGHT=0.4 STRUCTURE_WEIGHT=0.3 CONTENT_WEIGHT=0.3
```

`vlm_judge` 与 `anchor` 两种内容奖励仅在训练集上启用；测试集会回退到原始 TEDS。

## 3. 奖励依赖服务 —— `Uni_TabRL/server/`

内容 / 结构奖励依赖四个服务。每个服务独立运行为 HTTP / OpenAI 兼容服务，奖励
客户端通过读取 `configs/servers/` 下的端点列表（`"host:port"` 字符串列表）来发现
它们：

| 服务          | 作用                          | 配置文件                           |
| ------------- | ----------------------------- | ---------------------------------- |
| `HunyuanOCR`  | Anchor OCR 模型（vLLM）       | `configs/servers/hunyuan_ocr.json` |
| `HTML_render` | HTML 转图像渲染（Playwright） | `configs/servers/html_render.json` |
| `TEDS_judger` | TEDS / TEDS-S 评分（FastAPI） | `configs/servers/teds_judger.json` |
| `vlm_judge`   | VLM 一致性判别（vLLM）        | `configs/servers/vlm_judge.json`   |

用各自的 `run.sh` 启动服务（在脚本顶部填入你自己的资源 / 模型路径），再把得到的
`host:port` 端点写入对应的 JSON 文件。每个服务目录还附带一个 `ping_*.py` 健康检查
脚本。OpenAI 兼容的客户端会自动解析所部署的模型名，因此无需配置模型名称。

运行奖励前，设置渲染输出位置：

```bash
export OUTPUT_PATH=/your/output/root
export PROJECT_NAME=structab
export EXPERIMENT_NAME=uni_tabrl
```

## 4. 分析脚本 —— `analysis/`

- **`get_benchmark_statics.py`** —— 计算 **表 1** 的 benchmark 统计（数据量、
  平均行 / 列数、平均合并单元格数）。
- **`get_benchmark_with_cue.py`** —— 为 **图 4(a)** 的 _显式结构线索影响_ 研究
  构造四种提示变体（`direct`、`with_size`、`with_merge`、`with_both`）。
- **`structure_probe_experiment.ipynb`** —— **图 4(b)** 的 _早期纠错影响_ 探针实验：
  定位生成中第一个结构错误，修正后重新让模型生成，对比后续的错误率与生成置信度
  （logp）。

运行任何脚本前，请先填入你自己的数据路径（占位符均写作 `your/path/to/...`）。

## 环境依赖

```bash
pip install -r Uni_TabRL/server/utils/requirements.txt
```
