from __future__ import annotations

from .base import APIBase

API_TYPES = ("local_vllm", "openai_compat")


def get_api(api_type: str, **kwargs) -> APIBase:
    """Build an API instance.

    Args:
        api_type: one of ``"local_vllm"`` / ``"openai_compat"``
        **kwargs: forwarded to the concrete API class

    Returns:
        an ``APIBase`` subclass instance
    """
    if api_type == "local_vllm":
        from .local_vllm import LocalVLLMAPI

        return LocalVLLMAPI(**kwargs)
    if api_type == "openai_compat":
        from .openai_compat import OpenAICompatAPI

        return OpenAICompatAPI(**kwargs)

    raise ValueError(f"unsupported api_type: {api_type!r}, expected one of {API_TYPES}")
