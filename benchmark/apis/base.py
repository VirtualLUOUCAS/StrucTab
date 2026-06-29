"""APIBase: the minimal abstract base class shared by all API backends."""

from __future__ import annotations

from abc import ABC, abstractmethod


class APIBase(ABC):
    @abstractmethod
    def __call__(self, img_path: str | None, question: str, **kwargs) -> tuple[bool, str, str]:
        """Unified call interface.

        Args:
            img_path: local image path (``None`` for text-only tasks)
            question: the prompt text

        Returns:
            a ``(success, thinking, answer)`` tuple:
              - success: whether the call succeeded
              - thinking: the model think segment (may be empty)
              - answer: the model final reply
        """
        ...
