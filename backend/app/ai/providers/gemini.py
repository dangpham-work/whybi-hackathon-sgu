"""GeminiProvider – nhà cung cấp chính (Bảng 5.1). Chủ: Đăng (C1-02)."""

from typing import Any

from app.ai.providers.base import LLMResult


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any], *, model: str, temperature: float = 0
    ) -> LLMResult:
        # TODO(C1-02): gọi Gemini với response_schema, đo latency_ms
        raise NotImplementedError("C1-02")

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("C1-02")
