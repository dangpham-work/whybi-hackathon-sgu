"""LLM_MODE=fake – trả JSON mẫu theo schema để Thắng và Quyền chạy luồng phiên trước khi prompt
hoàn thiện (mục 3.3 kế hoạch). Mở rộng mẫu trả về trong thẻ C1-02."""

from typing import Any

from app.ai.providers.base import LLMResult


def _sample(schema: dict[str, Any], defs: dict[str, Any] | None = None) -> Any:
    """Sinh giá trị tối thiểu hợp lệ cho một JSON Schema (đủ cho model_json_schema() của Pydantic)."""
    defs = defs if defs is not None else schema.get("$defs", {})
    if "$ref" in schema:
        return _sample(defs[schema["$ref"].split("/")[-1]], defs)
    if "anyOf" in schema:
        if any(o.get("type") == "null" for o in schema["anyOf"]):
            return None
        return _sample(schema["anyOf"][0], defs)
    if schema.get("examples"):  # schema có ví dụ chuẩn (vd. JudgeResult cần đủ 5 tiêu chí)
        return schema["examples"][0]
    if "default" in schema:
        return schema["default"]
    if "enum" in schema:
        return schema["enum"][0]
    t = schema.get("type")
    if t == "object":
        return {k: _sample(v, defs) for k, v in schema.get("properties", {}).items()}
    if t == "array":
        return []
    if t in ("number", "integer"):
        return schema.get("minimum", 0)
    if t == "boolean":
        return False
    if schema.get("format") == "date-time":
        return "2026-01-01T00:00:00Z"
    if schema.get("format") == "uuid":
        return "00000000-0000-0000-0000-000000000000"
    return "mẫu"


class FakeProvider:
    name = "fake"

    def complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any], *, model: str = "fake", temperature: float = 0
    ) -> LLMResult:
        return LLMResult(data=_sample(schema), model="fake")

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 768 for _ in texts]
