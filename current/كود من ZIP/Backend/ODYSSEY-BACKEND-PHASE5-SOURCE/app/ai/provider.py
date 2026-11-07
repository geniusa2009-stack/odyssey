"""AI provider abstraction. Providers turn a structured request into raw text (JSON)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict

from app.ai.context import MissionContext

Topic = Literal["state_summary", "why", "decision_impact", "free_question"]


class AIRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    system_prompt: str
    user_prompt: str
    topic: Topic
    question: str
    context: MissionContext


class AIProviderError(RuntimeError):
    pass


class AIProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    async def complete(self, request: AIRequest) -> str:
        """Return the model's raw text (expected: JSON matching the ORION response schema)."""


class OpenAICompatibleProvider(AIProvider):
    """Any OpenAI-style ``/chat/completions`` endpoint (OpenRouter, Ollama, vLLM, …).

    Nothing is hard-coded: base URL, model and (optional) key come from settings. Ollama runs
    locally for free (``http://localhost:11434/v1``).
    """

    name = "openai_compatible"

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        model: str,
        api_key: str | None,
        timeout_seconds: float,
    ) -> None:
        self._client = client
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._key = api_key
        self._timeout = timeout_seconds

    async def complete(self, request: AIRequest) -> str:
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        body: dict[str, Any] = {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
        }
        try:
            resp = await self._client.post(
                self._url, json=body, headers=headers, timeout=self._timeout
            )
            resp.raise_for_status()
            data = resp.json()
            return str(data["choices"][0]["message"]["content"])
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
            raise AIProviderError(f"provider call failed: {type(exc).__name__}") from None
