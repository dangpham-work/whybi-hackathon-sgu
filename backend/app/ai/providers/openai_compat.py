"""OpenAICompatProvider – mọi API tương thích OpenAI (dùng làm model dự phòng). Chủ: Đăng (C1-02)."""

from typing import Any

from app.ai.providers.base import LLMResult


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    def complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any], *, model: str, temperature: float = 0
    ) -> LLMResult:
        # TODO(C1-02): POST {base_url}/chat/completions với response_format=json_schema
        raise NotImplementedError("C1-02")

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("C1-02")
