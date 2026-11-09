"""OpenAICompatProvider – mọi API tương thích OpenAI (dùng làm model dự phòng). Chủ: Đăng (C1-02).

POST {base_url}/chat/completions với response_format=json_schema (hoặc json_object cho máy chủ cũ),
POST {base_url}/embeddings. Gọi bằng httpx – không thêm SDK.
"""

import time
from typing import Any, Literal

import httpx

from app.ai.providers.base import (
    LLMResult,
    PermanentProviderError,
    TransientProviderError,
    classify_http_status,
    provider_json_schema,
)


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout_s: float = 30,
        json_mode: Literal["json_schema", "json_object"] = "json_schema",
        embedding_model: str = "text-embedding-3-small",
        embedding_dim: int = 768,
        http_client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._no_temperature: set[str] = set()  # model từ chối temperature tùy ý
        self.api_key = api_key
        self.model = model
        self.json_mode = json_mode
        self.embedding_model = embedding_model
        self.embedding_dim = embedding_dim
        self.http = http_client or httpx.Client(timeout=timeout_s)

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            r = self.http.post(f"{self.base_url}{path}", json=body, headers=headers)
        except httpx.TimeoutException as e:
            raise TransientProviderError(f"openai_compat timeout: {e}") from e
        except httpx.TransportError as e:
            raise TransientProviderError(f"openai_compat mạng lỗi: {e}") from e
        if r.status_code >= 400:
            raise classify_http_status(r.status_code)(f"openai_compat {r.status_code}: {r.text[:300]}")
        try:
            return r.json()
        except ValueError as e:
            raise TransientProviderError("openai_compat: phản hồi không phải JSON") from e

    def complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any], *, model: str, temperature: float = 0
    ) -> LLMResult:
        if self.json_mode == "json_schema" and schema:
            fmt = {
                "type": "json_schema",
                "json_schema": {
                    "name": str(schema.get("title") or "output")[:64],
                    "schema": provider_json_schema(schema),
                    "strict": False,
                },
            }
        else:
            fmt = {"type": "json_object"}
        body = {"model": model, "messages": messages, "response_format": fmt}
        if model not in self._no_temperature:
            body["temperature"] = temperature
        t0 = time.perf_counter()
        try:
            data = self._post("/chat/completions", body)
        except PermanentProviderError as e:
            # Một số model (dòng suy luận) chỉ nhận temperature mặc định ⇒ nhớ lại và thử lại không gửi tham số đó
            if "temperature" not in body or "temperature" not in str(e):
                raise
            self._no_temperature.add(model)
            body.pop("temperature")
            data = self._post("/chat/completions", body)
        latency = int((time.perf_counter() - t0) * 1000)
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise PermanentProviderError("openai_compat: thiếu choices[0].message.content") from e
        usage = data.get("usage") or {}
        return LLMResult(
            data=None,
            raw_text=text,
            model=model,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=latency,
        )

    def close(self) -> None:
        self.http.close()

    def embed(self, texts: list[str]) -> list[list[float]]:
        data = self._post(
            "/embeddings", {"model": self.embedding_model, "input": texts, "dimensions": self.embedding_dim}
        )
        return [d["embedding"] for d in sorted(data["data"], key=lambda d: d.get("index", 0))]
