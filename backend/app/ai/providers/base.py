"""Adapter cho nhà cung cấp AI – Hình 5.9, NFR-14. Nghiệp vụ chỉ phụ thuộc các Protocol này."""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class LLMResult:
    data: dict[str, Any]
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


@dataclass
class TranscriptResult:
    text: str
    confidence: float
    words: list[dict[str, Any]] = field(default_factory=list)  # [{word, confidence}]


class LLMProvider(Protocol):
    name: str

    def complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any], *, model: str, temperature: float = 0
    ) -> LLMResult: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class STTProvider(Protocol):
    def transcribe(self, audio: bytes, lang: str = "vi", hints: list[str] | None = None) -> TranscriptResult: ...


class TTSProvider(Protocol):
    def synthesize(self, text: str, voice: str = "vi-VN") -> bytes: ...
