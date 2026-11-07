from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Mọi schema API dùng camelCase ở JSON (khớp ví dụ mục 5.4.4), snake_case trong Python."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class ErrorBody(ApiModel):
    code: str
    message: str
    details: dict = {}


class ErrorResponse(ApiModel):
    error: ErrorBody


T = TypeVar("T")


class Page(ApiModel, Generic[T]):
    items: list[T]
    page: int = 1
    size: int = 20
    total: int = 0
