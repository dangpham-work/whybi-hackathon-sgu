"""Adapter cho nhà cung cấp AI – Hình 5.9, NFR-14. Nghiệp vụ chỉ phụ thuộc các Protocol này."""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class LLMResult:
    """Kết quả thô của một lời gọi. `data` có sẵn khi provider đã parse JSON; nếu không, gateway parse `raw_text`."""

    data: dict[str, Any] | None
    model: str
    raw_text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


@dataclass
class TranscriptResult:
    text: str
    confidence: float
    words: list[dict[str, Any]] = field(default_factory=list)  # [{word, confidence}]


class ProviderError(Exception):
    """Lỗi từ nhà cung cấp. Gateway quyết định thử lại hay chuyển dự phòng theo loại lỗi."""


class TransientProviderError(ProviderError):
    """Lỗi tạm thời: timeout, mất mạng, 429 hết hạn mức, 5xx ⇒ thử lại rồi chuyển dự phòng."""


class PermanentProviderError(ProviderError):
    """Lỗi cố định: sai khóa, yêu cầu sai, model không tồn tại ⇒ chuyển dự phòng ngay."""


class LLMProvider(Protocol):
    name: str
    model: str  # model mặc định của provider

    def complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any], *, model: str, temperature: float = 0
    ) -> LLMResult: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class STTProvider(Protocol):
    def transcribe(self, audio: bytes, lang: str = "vi", hints: list[str] | None = None) -> TranscriptResult: ...


class TTSProvider(Protocol):
    def synthesize(self, text: str, voice: str = "vi-VN") -> bytes: ...


def classify_http_status(status: int) -> type[ProviderError]:
    return TransientProviderError if status in (408, 409, 425, 429) or status >= 500 else PermanentProviderError


# Tập con JSON Schema mà Gemini structured output chấp nhận (tài liệu GenerateContentConfig.response_json_schema).
_ALLOWED_KEYS = {
    "$id", "$defs", "$ref", "$anchor", "type", "format", "title", "description", "enum", "items", "prefixItems",
    "minItems", "maxItems", "minimum", "maximum", "anyOf", "oneOf", "properties", "additionalProperties",
    "required", "propertyOrdering",
}  # fmt: skip


def provider_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Rút JSON Schema của Pydantic về tập con nhà cung cấp hiểu (bỏ examples, default, minLength…).
    Ràng buộc bị bỏ vẫn được Pydantic kiểm khi validate ở gateway."""

    def clean(node: Any, in_props: bool = False) -> Any:
        if isinstance(node, list):
            return [clean(n) for n in node]
        if not isinstance(node, dict):
            return node
        if in_props:  # node là map tên-thuộc-tính → schema
            return {k: clean(v) for k, v in node.items()}
        if "$ref" in node:
            return {"$ref": node["$ref"]}
        out: dict[str, Any] = {}
        for k, v in node.items():
            if k == "const":
                out["enum"] = [v]
            elif k in ("properties", "$defs"):
                out[k] = clean(v, in_props=True)
            elif k in _ALLOWED_KEYS:
                out[k] = clean(v) if isinstance(v, dict | list) and k not in ("required", "enum") else v
        return out

    return clean(schema)
