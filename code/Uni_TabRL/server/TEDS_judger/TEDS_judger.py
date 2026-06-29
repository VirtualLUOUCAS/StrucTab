import gc
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel
from TEDS_judger_utils import process_mllm_eval_task, process_simple_task

"""
一个基于 FastAPI 的规则解析任务评分服务
提供一个 /judge 接口，用于根据参考答案评估模型生成的解析结果的分数

使用方式：API 调用
URL: http://{host}:{port}/judge
方法: POST
请求体:
{
    "item": "单条 infer_rst 数据"
    "model_key": "模型响应的键名"
}
返回值:
{
    "reward": 最终得分 (0~1),
    "analysis": 打分的详细分析,
    "is_valid": 打分过程是否正常,
}
"""

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("teds_judger")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("TEDS Judger service starting...")
    yield
    logger.info("TEDS Judger service shutting down...")
    gc.collect()


app = FastAPI(
    title="TEDS Judger Service",
    description="Table parsing evaluation service using TEDS metric",
    lifespan=lifespan,
)


class JudgeMllmEvalRequest(BaseModel):
    """
    处理单个评测项，用于 mllm eval

    Args:
        item: 单条 infer_rst 数据，包含以下 key
            id, model_key, 参考答案
        model_key: 模型响应的键名

    Returns:
        包含评分结果的字典
    """

    item: dict
    model_key: str


@app.post("/judge/mllm_eval")
def judge_mllm_eval_api(req: JudgeMllmEvalRequest):
    return process_mllm_eval_task(req.item, req.model_key)


class JudgeSimpleRequest(BaseModel):
    """
    处理单个简单评测项

    Args:
        response: 模型生成的答案字符串
        ref_answer: 参考答案字符串
    """

    response: str
    ref_answer: str


@app.post("/judge/simple")
def judge_simple_api(req: JudgeSimpleRequest):
    return process_simple_task(req.response, req.ref_answer)
