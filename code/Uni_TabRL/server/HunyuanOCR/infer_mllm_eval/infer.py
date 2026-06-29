# -*- coding: utf-8 -*-
"""
改造版：使用多个 HunyuanOCR 端点进行负载均衡推理
"""

import argparse
import base64
import json
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from openai import OpenAI
from tqdm import tqdm

# 配置
DEFAULT_QUESTION = "把图中的表格解析为HTML。"
OUTPUT_LOCK = threading.Lock()  # 用于同步文件写入
MAX_WORKERS = 256
TIMEOUT = 180
SAVE_ERROR_ITEM = False

# HunyuanOCR 端点配置 (格式: "ip:port")
CONFIG = {
    "HunyuanOCR": [
        "your.host:port",
        "your.host:port",
    ]
}

# 输入输出配置
INPUT_FILES = ["your/path/to/input.jsonl"]

OUTPUT_DIR = "your/path/to/output_dir"


class ClientPool:
    """客户端池，用于管理多个 OpenAI 客户端"""

    def __init__(self, endpoints: list[str], model_name: str = "HYVL"):
        self.endpoints = endpoints
        self.model_name = model_name
        self.clients = {}

        # 初始化所有客户端
        for endpoint in endpoints:
            ip, port = endpoint.split(":")
            self.clients[endpoint] = OpenAI(
                base_url=f"http://{ip}:{port}/v1",
                api_key="EMPTY",
                timeout=TIMEOUT,
            )

        print(f"Initialized {len(self.clients)} clients")

    def get_random_client(self) -> tuple[OpenAI, str]:
        """随机选择一个客户端，返回 (client, endpoint)"""
        endpoint = random.choice(self.endpoints)
        return self.clients[endpoint], endpoint


def encode_base64(image_path: str) -> str:
    """将图片编码为 base64"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def build_messages(image_path: str, question: str, system_prompt: str = "") -> list[dict]:
    """构造适合 vLLM API 的消息格式"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    messages = [
        {"role": "system", "content": system_prompt if system_prompt else ""},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encode_base64(image_path)}"}},
                {"type": "text", "text": question},
            ],
        },
    ]
    return messages


def load_processed_ids(output_file: str) -> set[str]:
    """加载已处理的 ID"""
    processed_ids = set()
    if os.path.exists(output_file):
        with open(output_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if "HunyuanOCR_Eagle3_responses" in data:
                        processed_ids.add(data["id"])
                except json.JSONDecodeError:
                    continue
    return processed_ids


def process_single_item(item: dict, client_pool: ClientPool, args) -> dict:
    """处理单个数据项"""
    try:
        # 获取图片路径（取第一个）
        image_path = item["image_path"][0] if isinstance(item["image_path"], list) else item["image_path"]

        # 使用默认问题
        question = DEFAULT_QUESTION

        # 构建消息
        messages = build_messages(image_path, question, args.system_prompt)

        # 随机选择一个客户端
        client, endpoint = client_pool.get_random_client()

        # 调用 API
        completion = client.chat.completions.create(
            model=client_pool.model_name,
            messages=messages,
            top_p=args.top_p,
            seed=args.random_seed,
            temperature=args.temperature,
            stream=args.stream,
            extra_body={
                "top_k": args.top_k,
                "repetition_penalty": args.repetition_penalty,
            },
        )

        # 获取响应
        if args.stream:
            output_str = ""
            for output in completion:
                output_str += output.choices[0].delta.content
        else:
            output_str = completion.choices[0].message.content

        return {
            "status": "success",
            "item": item,
            "response": output_str,
            "endpoint": endpoint,
        }

    except FileNotFoundError as e:
        return {"status": "error", "item": item, "error": f"File not found: {str(e)}"}
    except Exception as e:
        return {"status": "error", "item": item, "error": str(e)}


def process_single_file(input_file: str, output_file: str, client_pool: ClientPool, args):
    """处理单个输入文件"""
    print(f"\n{'=' * 60}")
    print(f"Processing: {input_file}")
    print(f"Output to: {output_file}")
    print(f"{'=' * 60}")

    # 创建输出目录
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # 加载已处理的 ID
    processed_ids = load_processed_ids(output_file)
    print(f"Found {len(processed_ids)} already processed items")

    # 读取输入数据
    items_to_process = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                if item["id"] not in processed_ids:
                    items_to_process.append(item)

    print(f"Found {len(items_to_process)} items to process")

    if not items_to_process:
        print("No items to process, skipping...")
        return

    # 使用线程池并发处理
    success_count = 0
    error_count = 0

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = []
        for item in items_to_process:
            future = executor.submit(process_single_item, item, client_pool, args)
            futures.append(future)

        # 处理结果
        for future in tqdm(as_completed(futures), total=len(futures), desc="Processing"):
            result = future.result()
            item = result["item"]

            if result["status"] == "success":
                # 保存响应到指定字段（list of str，长度为 1）
                item["HunyuanOCR_Eagle3_responses"] = [result["response"]]
                success_count += 1
            else:
                if SAVE_ERROR_ITEM:
                    item["HunyuanOCR_Eagle3_responses"] = [f"ERROR: {result['error']}"]
                else:
                    print(f"Error processing item ID {item['id']}: {result['error']}")
                error_count += 1

            # 使用锁保护文件写入
            if SAVE_ERROR_ITEM or result["status"] == "success":
                with OUTPUT_LOCK:
                    with open(output_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps(item, ensure_ascii=False) + "\n")

            # 定期输出统计信息
            if (success_count + error_count) % 100 == 0:
                print(f"\nProgress: Success={success_count}, Error={error_count}, Total={len(items_to_process)}")

    print("\nProcessing completed:")
    print(f"Total items: {len(items_to_process)}")
    print(f"Success: {success_count}")
    print(f"Error: {error_count}")


def main(args):
    """主函数"""
    # 初始化客户端池
    client_pool = ClientPool(CONFIG["HunyuanOCR"], model_name=args.model_name)

    # 处理每个输入文件
    for input_file in INPUT_FILES:
        # 生成输出文件路径（与输入文件同名）
        input_filename = Path(input_file).name
        output_file = os.path.join(OUTPUT_DIR, input_filename)

        # 处理文件
        process_single_file(input_file, output_file, client_pool, args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HunyuanOCR batch inference with load balancing")
    parser.add_argument("--model_name", type=str, default="HYVL", help="Model name")
    parser.add_argument("--max_workers", type=int, default=MAX_WORKERS, help="Maximum number of threads")
    parser.add_argument("--system_prompt", type=str, default="", help="System prompt")
    parser.add_argument("--stream", action="store_true", default=False, help="Stream output")

    # Sampling parameters
    parser.add_argument("--top_k", type=int, default=64)
    parser.add_argument("--top_p", type=float, default=0.95)
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument("--repetition_penalty", type=float, default=1.0)
    parser.add_argument("--random_seed", type=int, default=1234)

    args = parser.parse_args()

    start_time = time.time()
    main(args)
    print(f"\nAll processing completed in {time.time() - start_time:.2f} seconds")
