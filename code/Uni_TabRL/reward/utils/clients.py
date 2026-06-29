import os
import random
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

import requests
from openai import OpenAI
from openai.types.chat.chat_completion import ChatCompletion

from .io import encode_image
from .servers import (
    get_html_render_servers,
    get_hunyuan_ocr_servers,
    get_teds_judger_servers,
    get_vlm_judge_servers,
)

# Service routes
TEDS_JUDGE_ROUTE = "/judge/simple"
RENDER_SINGLE_ROUTE = "/render/single"
RENDER_DUAL_ROUTE = "/render/dual"

# Default OCR prompt for the Anchor OCR model
DEFAULT_OCR_QUESTION = "把图中的表格解析为HTML。"
DEFAULT_SYSTEM_PROMPT = ""


class ClientResponse:
    """Unified response wrapper for all reward service clients."""

    def __init__(self, success: bool, data: Optional[dict[str, Any]] = None, error: Optional[str] = None):
        self.success = success
        self.data = data or {}
        self.error = error

    def __bool__(self):
        return self.success

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def to_dict(self) -> dict[str, Any]:
        if self.success:
            return self.data
        return {"is_valid": False, "error": self.error or "Service unavailable"}


class BaseClient(ABC):
    """
    Base class for distributed service clients with round-robin load balancing.

    The server list is shuffled once and traversed twice before being reshuffled,
    spreading requests across all endpoints. Implemented as a thread-safe singleton.
    """

    _instances: dict[str, Any] = {}
    _lock = threading.Lock()

    def __new__(cls):
        class_name = cls.__name__
        if class_name not in cls._instances:
            with cls._lock:
                if class_name not in cls._instances:
                    cls._instances[class_name] = super().__new__(cls)
        return cls._instances[class_name]

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._state = {"index": 0, "shuffled_servers": []}
        self._init_or_reshuffle_servers()
        self._initialized = True

    @abstractmethod
    def _get_server_list(self) -> list[str]:
        """Return the list of ``host:port`` endpoints (implemented by subclass)."""
        pass

    @abstractmethod
    def _build_server_url(self, host: str) -> str:
        """Build the full request URL for a given endpoint (implemented by subclass)."""
        pass

    def _init_or_reshuffle_servers(self):
        hosts = self._get_server_list()
        self.servers = [self._build_server_url(host) for host in hosts]

        if not self.servers:
            self._state["shuffled_servers"] = []
            return

        shuffled = list(self.servers)
        random.shuffle(shuffled)
        self._state["index"] = 0
        self._state["shuffled_servers"] = shuffled

    def get_next_server(self) -> Optional[str]:
        """Return the next endpoint, reshuffling after two full passes."""
        with self._lock:
            shuffled_servers = self._state["shuffled_servers"]
            if not shuffled_servers:
                return None

            current_index = self._state["index"]
            if current_index >= len(shuffled_servers) * 2:
                self._init_or_reshuffle_servers()
                shuffled_servers = self._state["shuffled_servers"]
                current_index = 0

            server = shuffled_servers[current_index % len(shuffled_servers)]
            self._state["index"] = current_index + 1
            return server

    def _sleep_on_retry(self, attempt: int, max_retry: int):
        if attempt >= max_retry - 5:
            time.sleep(1.5)
        elif attempt >= max_retry // 2:
            time.sleep(1)
        else:
            time.sleep(0.5)


class TedsJudgeClient(BaseClient):
    """
    Client for the TEDS / TEDS-S scoring service.

    Input:
        - response:   predicted HTML table string
        - ref_answer: reference HTML table string

    Output (ClientResponse.data):
        - teds, teds_s : the two similarity scores
    """

    def __init__(self):
        self.judge_route = TEDS_JUDGE_ROUTE
        super().__init__()

    def _get_server_list(self) -> list[str]:
        return get_teds_judger_servers()

    def _build_server_url(self, host: str) -> str:
        return f"http://{host}{self.judge_route}"

    def call(self, response: str, ref_answer: str, max_retry: int = 5) -> ClientResponse:
        payload = {"response": response, "ref_answer": ref_answer}

        for attempt in range(max_retry):
            url = self.get_next_server()
            if url is None:
                continue
            try:
                resp = requests.post(url, json=payload, timeout=10)
                if resp.status_code == 200:
                    return ClientResponse(success=True, data=resp.json())
            except Exception as e:
                if attempt == max_retry - 1:
                    error_msg = f"TEDS judge service failed after {max_retry} attempts: {e}"
                    print(error_msg)
                    return ClientResponse(success=False, error=error_msg)
            self._sleep_on_retry(attempt, max_retry)

        return ClientResponse(success=False, error="TEDS judge service unreachable")


class RenderClient(BaseClient):
    """
    Client for the HTML-to-image rendering service.

    ``render_single`` renders one table; ``render_dual`` renders two tables
    side by side (used to build the input image for the VLM judge).

    Output (ClientResponse.data):
        - image_path : absolute path of the rendered image
    """

    def __init__(self):
        self.render_single_route = RENDER_SINGLE_ROUTE
        self.render_dual_route = RENDER_DUAL_ROUTE
        self.prepared_dirs = set()
        super().__init__()

    def _get_server_list(self) -> list[str]:
        return get_html_render_servers()

    def _build_server_url(self, host: str) -> str:
        return f"http://{host}"

    def _makedirs(self, path: str, mode: int = 0o777):
        if path in self.prepared_dirs:
            return
        os.makedirs(path, exist_ok=True)
        os.chmod(path, mode)
        self.prepared_dirs.add(path)

    def render_single(self, content: str, image_name: str, output_dir: str, max_retry: int = 5) -> ClientResponse:
        payload = {"content": content, "image_name": image_name, "output_dir": output_dir}
        self._makedirs(output_dir)
        return self._call_render(payload, self.render_single_route, max_retry)

    def render_dual(
        self, content_left: str, content_right: str, image_name: str, output_dir: str, max_retry: int = 5
    ) -> ClientResponse:
        payload = {
            "content_left": content_left,
            "content_right": content_right,
            "image_name": image_name,
            "output_dir": output_dir,
        }
        self._makedirs(output_dir)
        return self._call_render(payload, self.render_dual_route, max_retry)

    def _call_render(self, payload: dict[str, str], route: str, max_retry: int) -> ClientResponse:
        for attempt in range(max_retry):
            server = self.get_next_server()
            if server is None:
                continue
            url = server + route
            try:
                resp = requests.post(url, json=payload, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("image_path"):
                        return ClientResponse(success=True, data=data)
            except Exception as e:
                if attempt == max_retry - 1:
                    error_msg = f"Render service failed after {max_retry} attempts: {e}"
                    print(error_msg)
                    return ClientResponse(success=False, error=error_msg)
            self._sleep_on_retry(attempt, max_retry)

        return ClientResponse(success=False, error="Render service unreachable")


class _OpenAICompatClient(BaseClient):
    """
    Shared base for OpenAI-compatible (vLLM) services.

    The served model name is resolved dynamically via ``client.models.list()``,
    so no hard-coded model name is required.
    """

    def __init__(self):
        self.api_key = "EMPTY"
        self.top_p = 0.95
        self.top_k = 64
        self.temperature = 0.0
        self.repetition_penalty = 1.0
        self.random_seed = 1234
        super().__init__()

    def _build_server_url(self, host: str) -> str:
        return f"http://{host}/v1"

    def _build_messages(self, image_path: str, question: str, system_prompt: str) -> list[dict[str, Any]]:
        return [
            {"role": "system", "content": system_prompt or ""},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encode_image(image_path)}"}},
                    {"type": "text", "text": question},
                ],
            },
        ]

    def _chat(self, image_path: str, question: str, system_prompt: str, max_retry: int, timeout: int) -> ClientResponse:
        messages = self._build_messages(image_path, question, system_prompt)

        for attempt in range(max_retry):
            url = self.get_next_server()
            if url is None:
                continue
            client = OpenAI(api_key=self.api_key, base_url=url, timeout=timeout)
            try:
                # Resolve the served model name dynamically (no hard-coded name needed).
                model_name = client.models.list().data[0].id
                completion: ChatCompletion = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    top_p=self.top_p,
                    seed=self.random_seed,
                    temperature=self.temperature,
                    stream=False,
                    extra_body={"top_k": self.top_k, "repetition_penalty": self.repetition_penalty},
                )
                return ClientResponse(success=True, data={"output": completion.choices[0].message.content})
            except Exception as e:
                if attempt == max_retry - 1:
                    error_msg = f"{self.__class__.__name__} failed after {max_retry} attempts: {e}"
                    print(error_msg)
                    return ClientResponse(success=False, error=error_msg)
            self._sleep_on_retry(attempt, max_retry)

        return ClientResponse(success=False, error=f"{self.__class__.__name__} unreachable")


class HunyuanOcrClient(_OpenAICompatClient):
    """
    Client for the HunyuanOCR Anchor OCR model (OpenAI-compatible vLLM service).

    Input:
        - image_path : path of the rendered table image
    Output (ClientResponse.data):
        - output : the parsed HTML produced by HunyuanOCR
    """

    def _get_server_list(self) -> list[str]:
        return get_hunyuan_ocr_servers()

    def call(
        self,
        image_path: str,
        question: str = DEFAULT_OCR_QUESTION,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_retry: int = 5,
        timeout: int = 30,
    ) -> ClientResponse:
        return self._chat(image_path, question, system_prompt, max_retry, timeout)


class VlmJudgeClient(_OpenAICompatClient):
    """
    Client for the VLM-as-judge service (OpenAI-compatible vLLM service).

    Given an image that contains the rendered prediction and reference tables
    side by side, the VLM decides whether the two tables are visually consistent.

    Input:
        - image_path    : path of the dual-rendered comparison image
        - question      : user prompt
        - system_prompt : system prompt describing the judging rubric
    Output (ClientResponse.data):
        - output : the raw VLM response (expected to contain a JSON verdict)
    """

    def _get_server_list(self) -> list[str]:
        return get_vlm_judge_servers()

    def call(
        self,
        image_path: str,
        question: str,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_retry: int = 5,
        timeout: int = 60,
    ) -> ClientResponse:
        return self._chat(image_path, question, system_prompt, max_retry, timeout)
