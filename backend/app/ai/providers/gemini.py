"""GeminiProvider – nhà cung cấp chính (Bảng 5.1). Chủ: Đăng (C1-02).

SDK `google-genai` (from google import genai): structured output bằng `response_json_schema` +
`response_mime_type="application/json"`; timeout qua `HttpOptions.timeout` (mili giây). SDK không tự thử lại
(attempts=1) – gateway lo thử lại và chuyển dự phòng.
"""

import time
from typing import Any

import httpx
from google import genai
from google.genai import errors, types

from app.ai.providers.base import (
    LLMResult,
    PermanentProviderError,
    TransientProviderError,
    classify_http_status,
    provider_json_schema,
)


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout_s: float = 30,
        embedding_model: str = "gemini-embedding-001",
        embedding_dim: int = 768,
        client: Any | None = None,
    ):
        self.model = model
        self.embedding_model = embedding_model
        self.embedding_dim = embedding_dim
        self.client = client or genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(timeout_s * 1000), retry_options=types.HttpRetryOptions(attempts=1)
            ),
        )

    @staticmethod
    def _split(messages: list[dict[str, str]]) -> tuple[str | None, list[dict[str, Any]]]:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system") or None
        contents = [
            {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
            for m in messages
            if m["role"] != "system"
        ]
        return system, contents

    def _call(self, fn, **kwargs):
        try:
            return fn(**kwargs)
        except errors.APIError as e:
            raise classify_http_status(e.code or 500)(f"gemini {e.code}: {e.message}") from e
        except httpx.TimeoutException as e:
            raise TransientProviderError(f"gemini timeout: {e}") from e
        except httpx.TransportError as e:
            raise TransientProviderError(f"gemini mạng lỗi: {e}") from e

    def complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any], *, model: str, temperature: float = 0
    ) -> LLMResult:
        system, contents = self._split(messages)
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
            response_json_schema=provider_json_schema(schema) if schema else None,
        )
        t0 = time.perf_counter()
        resp = self._call(self.client.models.generate_content, model=model, contents=contents, config=config)
        latency = int((time.perf_counter() - t0) * 1000)
        text = resp.text
        if text is None:  # bị chặn an toàn hoặc hết token – coi như lỗi cố định với lời gọi này
            raise PermanentProviderError("gemini: phản hồi rỗng")
        usage = resp.usage_metadata
        return LLMResult(
            data=None,
            raw_text=text,
            model=model,
            input_tokens=(usage.prompt_token_count or 0) if usage else 0,
            output_tokens=(usage.candidates_token_count or 0) if usage else 0,
            latency_ms=latency,
        )

    def close(self) -> None:
        close = getattr(self.client, "close", None)
        if close is not None:
            close()

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self._call(
            self.client.models.embed_content,
            model=self.embedding_model,
            contents=texts,
            config=types.EmbedContentConfig(output_dimensionality=self.embedding_dim),
        )
        return [list(e.values or []) for e in resp.embeddings or []]
