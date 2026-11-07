import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Quy ước đặt tên ràng buộc để Alembic sinh migration ổn định
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class UUIDPk:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def in_values(column: str, values) -> str:
    """Biểu thức CHECK "cột IN (...)" từ một StrEnum – thêm giá trị enum thì cần migration mới (Long)."""
    return f"{column} IN ({', '.join(repr(str(v.value)) for v in values)})"


def range_check(column: str, low: float, high: float, nullable: bool = True) -> str:
    expr = f"{column} BETWEEN {low} AND {high}"
    return f"{column} IS NULL OR {expr}" if nullable else expr


def created_at_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
