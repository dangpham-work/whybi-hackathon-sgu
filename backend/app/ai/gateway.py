"""LLM Gateway – HỢP ĐỒNG DỮ LIỆU #3 (Bảng 7 kế hoạch): call_json(schema, messages) trả đối tượng
đúng schema; có cache, model dự phòng, thử lại khi lỗi parse, ngân sách token, LLM_MODE=fake.
Chủ: Đăng (C1-02) · Hạn: H2 · Bên dùng: mọi tác tử và pipeline giáo trình.
"""

from typing import TypeVar

from pydantic import BaseModel

from app.ai.providers.base import LLMProvider
from app.ai.providers.fake import FakeProvider
from app.core.config import get_settings

T = TypeVar("T", bound=BaseModel)


class LLMGateway:
    def __init__(self, primary: LLMProvider, fallback: LLMProvider | None = None, max_retries: int = 2):
        self.primary = primary
        self.fallback = fallback
        self.max_retries = max_retries

    def call_json(self, schema: type[T], messages: list[dict[str, str]], *, model: str | None = None) -> T:
        """Gọi LLM, ép JSON theo `schema`, trả về instance đã validate.

        TODO(C1-02): cache theo hash(messages), retry khi ValidationError (tối đa 2 lần, kèm thông báo
        lỗi schema – UC06 luồng 4a), chuyển model dự phòng khi lỗi/hết hạn mức (E2), kiểm ngân sách
        token phiên (NFR-13), log latency_ms.
        """
        settings = get_settings()
        result = self.primary.complete(messages, schema.model_json_schema(), model=model or settings.llm_model)
        return schema.model_validate(result.data)


def get_gateway() -> LLMGateway:
    settings = get_settings()
    if settings.llm_mode == "fake":
        return LLMGateway(FakeProvider())
    raise NotImplementedError("C1-02: dựng GeminiProvider / OpenAICompatProvider từ cấu hình")
