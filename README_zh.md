# StrucTab <!-- omit in toc -->

**面向表格解析的结构化优化框架**

<p align="center">
  <a href="README.md">English Version</a> •
  <a href="https://github.com/VirtualLUOUCAS/StrucTab">GitHub 仓库</a> •
  <a href="https://huggingface.co/datasets/psp-dada/TableVerse-5K">HuggingFace 数据集</a> •
  <a href="https://modelscope.cn/datasets/pspdada/TableVerse-5K">ModelScope 数据集</a> •
  <a href="https://arxiv.org/abs/2606.29905">论文</a>
</p>

## 新闻 <!-- omit in toc -->

- [2026.06] 📖 代码与 TableVerse-5K 基准已发布！
- [2026.06] 🎉 我们的 StrucTab 已被 **ECCV 2026** 接收！

## 概览 <!-- omit in toc -->

**StrucTab** 是一个面向**表格解析（table parsing）**任务的结构化优化框架，目标是将表格图像转换为结构化的 HTML。与将解析视为扁平的图像到文本问题不同，StrucTab 将其分解为三个相互耦合的子任务，即行列计数、合并单元格分析与最终 HTML 生成，并优化一个沿相同维度（`validity`、`structure`、`content`）分解的强化学习奖励。

<table align="center">
    <p align="center">
      <img src="/docs/figures/introduction.jpg" width="80%" />
    </p>
</table>

## 目录 <!-- omit in toc -->

- [仓库结构](#仓库结构)
- [代码](#代码)
- [基准](#基准)
- [引用](#引用)
- [许可证](#许可证)

## 仓库结构

本仓库开源了：

- **`code/`** —— 训练数据构造流程、Uni-TabRL 奖励、其四个依赖服务，以及生成论文图表所用的分析脚本。
- **`benchmark/`** —— 面向 **TableVerse-5K** 表格解析基准的自包含推理与评测框架，使用结构感知的 TEDS / TEDS-S 指标评分。

<details>
<summary>完整目录树（点击展开）</summary>

```
StrucTab/
├── README.md
├── code/                         # 训练 + RL 奖励 + 分析（见 code/README.md）
│   ├── training_data/            # 从 (图像, HTML) 对构造序列推理数据
│   ├── Uni_TabRL/
│   │   ├── reward/               # 分解式 RL 奖励（validity / structure / content）
│   │   ├── server/               # 四个奖励依赖服务
│   │   │   └── TEDS_judger/      # TEDS / TEDS-S 打分服务（基准也会复用）
│   │   └── configs/servers/      # 奖励服务的端点列表
│   └── analysis/                 # 生成论文图表的脚本
└── benchmark/                    # TableVerse-5K 的推理 + 评测框架
    ├── apis/                     # 可插拔后端：openai_compat | local_vllm
    ├── utils/                    # 增量写入器、图片编码、信号处理
    ├── data/                     # ← 在此放置 TableVerse-5K 数据集
    ├── infer.py                  # 入口：推理  → infer_results/<tag>/results.jsonl
    ├── judge.py                  # 入口：TEDS 评分 → judge_results/<tag>/results.jsonl
    ├── judger_server.json        # TEDS 服务端点列表（host:port）
    └── requirements.txt
```

</details>

## 代码

模型侧代码（训练数据构造、Uni-TabRL 奖励、四个依赖服务，以及分析脚本）单独说明于
[`code/README.md`](code/README.md)（中文版：[`code/README_zh.md`](code/README_zh.md)）。

强化学习的优化框架如下：

<table align="center">
    <p align="center">
      <img src="/docs/figures/optimization_framework.jpg" width="80%" />
    </p>
</table>

## 基准

`benchmark/` 是面向 **TableVerse-5K** 表格解析基准的自包含框架。它运行 **推理 → 评测** 两阶段流程，支持可插拔的 API 后端（`openai_compat` / `local_vllm`）与结构感知的 **TEDS / TEDS-S** 评分器。两个阶段都以样本的 `image_path` 为主键，支持**断点续跑**。

完整的环境准备、数据下载，以及推理 / 评测的分步说明，请见
[`benchmark/README_zh.md`](benchmark/README_zh.md)（English：[`benchmark/README.md`](benchmark/README.md)）。

基准的数据集构建流程如下：

<table align="center">
    <p align="center">
      <img src="/docs/figures/benchmark_pipeline.jpg" width="80%" />
    </p>
</table>

## 引用

如果 StrucTab 对你有帮助，欢迎引用：

```bibtex
TBD
```

## 许可证

本项目仅供**学术研究使用**。
