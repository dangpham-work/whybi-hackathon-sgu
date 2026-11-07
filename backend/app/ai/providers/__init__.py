"""Sổ đăng ký nhà cung cấp LLM: đổi nhà cung cấp chỉ bằng cấu hình (LLM_PROVIDER / LLM_FALLBACK_PROVIDER
hoặc PUT /admin/ai-config), không sửa code nghiệp vụ (NFR-14)."""

from app.ai.providers.base import LLMProvider
from app.ai.providers.fake import FakeProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.openai_compat import OpenAICompatProvider
from app.core.config import Settings
from app.core.errors import AppError

PROVIDERS = ("gemini", "openai_compat", "fake")


def build_provider(name: str, model: str, settings: Settings) -> LLMProvider:
    if name == "gemini":
        if not settings.gemini_api_key:
            raise AppError(503, "LLM_NOT_CONFIGURED", "Thiếu GEMINI_API_KEY", {"provider": name})
        return GeminiProvider(
            settings.gemini_api_key,
            model,
            timeout_s=settings.llm_timeout_s,
            embedding_model=settings.llm_embedding_model,
            embedding_dim=settings.embedding_dim,
        )
    if name == "openai_compat":
        if not settings.openai_compat_base_url:
            raise AppError(503, "LLM_NOT_CONFIGURED", "Thiếu OPENAI_COMPAT_BASE_URL", {"provider": name})
        return OpenAICompatProvider(
            settings.openai_compat_base_url,
            settings.openai_compat_api_key,
            model,
            timeout_s=settings.llm_timeout_s,
            json_mode=settings.openai_compat_json_mode,
            embedding_dim=settings.embedding_dim,
        )
    if name == "fake":
        return FakeProvider()
    raise AppError(422, "UNKNOWN_PROVIDER", f"Nhà cung cấp LLM không hỗ trợ: {name}", {"allowed": list(PROVIDERS)})


__all__ = ["PROVIDERS", "FakeProvider", "GeminiProvider", "LLMProvider", "OpenAICompatProvider", "build_provider"]
