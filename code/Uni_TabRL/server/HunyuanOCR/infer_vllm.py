# -*- coding: utf-8 -*-
import argparse
import base64
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI
from tqdm import tqdm

OUTPUT_LOCK = threading.Lock()  # 用于同步文件写入
DEFAULT_QUESTION = "把图中的表格解析为HTML。"


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


def load_processed_data(output_file):
    """加载已处理的数据"""
    processed_data = set()
    if os.path.exists(output_file):
        with open(output_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if "extra_info" in data and "vllm_response" in data:
                        processed_data.add(data["extra_info"]["render_ref_answer"]["image_path"])
                except json.JSONDecodeError:
                    continue
    return processed_data


def process_single_item(item, client: OpenAI, args):
    """处理单个数据项"""
    try:
        # 构建完整的图片路径
        image_path = item["extra_info"]["render_ref_answer"]["image_path"]
        question = DEFAULT_QUESTION

        # 生成请求消息
        messages = build_messages(image_path, question, args.system_prompt)

        # 调用 API
        completion = client.chat.completions.create(
            model=args.model_name,
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

        return {"status": "success", "item": item, "response": output_str}

    except FileNotFoundError as e:
        print(f"\nFile not found error for {item.get('extra_info', 'unknown')}: {str(e)}")
        return {"status": "error", "item": item, "error": f"File not found: {str(e)}"}
    except Exception as e:
        print(f"\nError processing {item.get('extra_info', 'unknown')}: {str(e)}")
        return {"status": "error", "item": item, "error": str(e)}


def process_json(input_file, output_file, args):
    client = OpenAI(
        base_url=f"http://{args.ip}:{args.port}/v1",
        api_key="EMPTY",
    )

    # 加载已处理的数据
    processed_data = load_processed_data(output_file)
    print(f"Found {len(processed_data)} processed items")

    # 读取输入数据
    items_to_process = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                if item["extra_info"]["render_ref_answer"]["image_path"] not in processed_data:
                    items_to_process.append(item)

    print(f"Found {len(items_to_process)} items to process")

    # 使用线程池并发处理
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = []
        for item in items_to_process:
            future = executor.submit(process_single_item, item, client, args)
            futures.append(future)

        # 处理结果
        success_count = 0
        error_count = 0

        for future in tqdm(as_completed(futures), total=len(futures), desc="Processing"):
            result = future.result()
            item = result["item"]

            if result["status"] == "success":
                item["vllm_response"] = result["response"]
                success_count += 1
            else:
                item["vllm_response"] = f"ERROR: {result['error']}"
                error_count += 1

            # 使用锁保护文件写入
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", type=str, default="localhost", help="gpt server ip")
    parser.add_argument("--port", type=int, default=8021, help="gpt server port")
    parser.add_argument("--model_name", type=str, default="HYVL", help="gpt model name")
    parser.add_argument("--max_workers", type=int, default=6, help="maximum number of threads")
    parser.add_argument("--request_id", type=str, default="0", help="request id")
    parser.add_argument("--system_prompt", type=str, default="", help="")
    parser.add_argument("--input_jsonl", type=str, required=True, help="Input jsonl file path")
    parser.add_argument("--output_jsonl", type=str, required=True, help="Output jsonl file path")
    parser.add_argument("--output_len", type=int, default=8192, required=False)
    parser.add_argument("--stream", action="store_true", default=False, help="stream output")

    # Sampling parameters
    parser.add_argument("--top_k", type=int, default=64)
    parser.add_argument("--top_p", type=float, default=0.95)
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument("--repetition_penalty", type=float, default=1.0)
    parser.add_argument("--random_seed", type=int, default=1234)

    args = parser.parse_args()

    start_time = time.time()
    process_json(args.input_jsonl, args.output_jsonl, args)
    print(f"Processing completed in {time.time() - start_time:.2f} seconds")
