"""Hạn mức token LLM và phút ghi âm theo lớp / theo SV (FR-AD-06, NFR-13). Chủ: Long (C2-18).

- QTV đặt hạn mức (`usage_quotas`); mức đã dùng cộng từ `usage_records` (mỗi phiên một dòng).
- Orchestrator gọi `check` trước khi nhận việc (bắt đầu phiên, gửi lượt, tải ghi âm) và `record_tokens` / `add_audio`
  sau đó. Vượt hạn mức ⇒ 429 QUOTA_EXCEEDED kèm thông báo tiếng Việt cho SV.
- Token lấy từ ngân sách theo phiên của LLMGateway (đặt tuyệt đối, không cộng dồn nên gọi lặp vẫn đúng).
"""

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ai.gateway import get_current_ai_config
from app.core.errors import AppError
from app.db.base import utcnow
from app.models.peer import UsageQuota, UsageRecord
from app.models.schemas.admin import QuotaIn, QuotaOut, UsageStatsOut
from app.models.users import ClassSection, User

log = logging.getLogger(__name__)

CLASS, STUDENT = "CLASS", "STUDENT"
_COLUMN = {CLASS: UsageRecord.class_id, STUDENT: UsageRecord.student_id}


def estimate_audio_seconds(data: bytes, ext: str) -> int:
    """Thời lượng ghi âm để tính hạn mức. WAV đọc đúng từ tiêu đề; định dạng nén chỉ ước lượng theo dung lượng và
    cố ý lấy bitrate THẤP (opus 16 kbps, mp3/m4a 64 kbps) để không đếm hụt khi ai đó gửi tệp bitrate rất thấp:
    ghi âm thường (opus ~32 kbps) bị tính dư tới ~2 lần.
    # ponytail: ước lượng theo bitrate sàn; STT hoặc bộ đọc container trả thời lượng thật thì thay."""
    if ext == "wav":
        from app.services.speech import _wav_seconds

        return round(_wav_seconds(data))
    bytes_per_second = 2_000 if ext in ("webm", "ogg") else 8_000
    return max(1, round(len(data) / bytes_per_second))


class QuotaService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ QTV đặt / xem

    def _name(self, scope: str, scope_id: UUID) -> str | None:
        if scope == CLASS:
            return self.db.scalar(select(ClassSection.name).where(ClassSection.id == scope_id))
        return self.db.scalar(select(User.full_name).where(User.id == scope_id))

    def usage(self, scope: str, scope_id: UUID) -> tuple[int, int]:
        """(token, giây ghi âm) đã dùng."""
        col = _COLUMN[scope]
        row = self.db.execute(
            select(
                func.coalesce(func.sum(UsageRecord.tokens), 0), func.coalesce(func.sum(UsageRecord.audio_seconds), 0)
            ).where(col == scope_id)
        ).one()
        return int(row[0]), int(row[1])

    def _out(self, q: UsageQuota) -> QuotaOut:
        tokens, seconds = self.usage(q.scope, q.scope_id)
        return QuotaOut(
            scope=q.scope,
            scope_id=q.scope_id,
            token_limit=q.token_limit,
            audio_minutes_limit=q.audio_minutes_limit,
            name=self._name(q.scope, q.scope_id),
            tokens_used=tokens,
            audio_minutes_used=round(seconds / 60, 1),
        )

    def list(self, scope: str | None = None) -> list[QuotaOut]:
        q = select(UsageQuota).order_by(UsageQuota.scope, UsageQuota.updated_at.desc())
        if scope:
            q = q.where(UsageQuota.scope == scope)
        return [self._out(r) for r in self.db.scalars(q)]

    def set(self, body: QuotaIn) -> QuotaOut:
        """Đặt (hoặc bỏ nếu cả hai giới hạn là null) hạn mức. Lớp / SV không tồn tại ⇒ 404."""
        if self._name(body.scope, body.scope_id) is None:
            code = "CLASS_NOT_FOUND" if body.scope == CLASS else "STUDENT_NOT_FOUND"
            raise AppError(404, code, "Không tìm thấy lớp" if body.scope == CLASS else "Không tìm thấy sinh viên")
        row = self.db.scalar(
            select(UsageQuota).where(UsageQuota.scope == body.scope, UsageQuota.scope_id == body.scope_id)
        )
        if body.token_limit is None and body.audio_minutes_limit is None:
            if row is not None:
                self.db.delete(row)
                self.db.flush()
            return QuotaOut(**body.model_dump(), name=self._name(body.scope, body.scope_id))
        if row is None:
            row = UsageQuota(scope=body.scope, scope_id=body.scope_id)
            self.db.add(row)
        row.token_limit, row.audio_minutes_limit = body.token_limit, body.audio_minutes_limit
        row.updated_at = utcnow()
        self.db.flush()
        return self._out(row)

    # ------------------------------------------------------------------ chặn khi vượt

    def check(self, student_id: UUID, class_id: UUID, *, audio: bool = False) -> None:
        """429 QUOTA_EXCEEDED khi lớp hoặc SV đã chạm hạn mức token (mặc định) / phút ghi âm (`audio=True`)."""
        quotas = self.db.scalars(
            select(UsageQuota).where(
                ((UsageQuota.scope == CLASS) & (UsageQuota.scope_id == class_id))
                | ((UsageQuota.scope == STUDENT) & (UsageQuota.scope_id == student_id))
            )
        ).all()
        for q in quotas:
            limit = q.audio_minutes_limit if audio else q.token_limit
            if limit is None:
                continue
            tokens, seconds = self.usage(q.scope, q.scope_id)
            used, cap = (seconds / 60, limit) if audio else (tokens, limit)
            if used >= cap:
                who = "Lớp" if q.scope == CLASS else "Bạn"
                what = "phút ghi âm" if audio else "token AI"
                raise AppError(
                    429,
                    "QUOTA_EXCEEDED",
                    f"{who} đã dùng hết hạn mức {what} – liên hệ quản trị viên hoặc giảng viên",
                    {
                        "scope": q.scope,
                        "kind": "AUDIO_MINUTES" if audio else "TOKENS",
                        "limit": cap,
                        "used": round(used, 1),
                    },
                )

    # ------------------------------------------------------------------ ghi mức dùng

    def record_tokens(self, session_id: UUID, student_id: UUID, class_id: UUID, tokens: int) -> None:
        """Đặt số token của phiên (tuyệt đối, chỉ tăng), kèm provider/model LLM đang cấu hình lúc ghi (C2-24,
        để thống kê theo provider/model). Không commit."""
        cfg = get_current_ai_config()
        stmt = insert(UsageRecord).values(
            session_id=session_id,
            student_id=student_id,
            class_id=class_id,
            tokens=tokens,
            audio_seconds=0,
            provider=cfg["provider"],
            model=cfg["model"],
        )
        self.db.execute(
            stmt.on_conflict_do_update(
                index_elements=["session_id"],
                set_={
                    "tokens": func.greatest(UsageRecord.tokens, stmt.excluded.tokens),
                    "provider": stmt.excluded.provider,
                    "model": stmt.excluded.model,
                    "updated_at": utcnow(),
                },
            )
        )

    def usage_by_model(self) -> "list[UsageStatsOut]":  # "list" đã bị hàm list() của class này che ở module này
        """Token / phút ghi âm đã dùng, cộng theo provider + model (bổ sung FR-AD-06, demo C2-24)."""
        rows = self.db.execute(
            select(
                UsageRecord.provider,
                UsageRecord.model,
                func.coalesce(func.sum(UsageRecord.tokens), 0),
                func.coalesce(func.sum(UsageRecord.audio_seconds), 0),
                func.count(UsageRecord.id),
            )
            .group_by(UsageRecord.provider, UsageRecord.model)
            .order_by(func.coalesce(func.sum(UsageRecord.tokens), 0).desc())
        ).all()
        return [
            UsageStatsOut(
                provider=provider or "chưa rõ",
                model=model or "chưa rõ",
                tokens_used=int(tokens),
                audio_minutes_used=round(seconds / 60, 1),
                session_count=int(n),
            )
            for provider, model, tokens, seconds, n in rows
        ]

    def reserve_audio(self, session_id: UUID, student_id: UUID, class_id: UUID, seconds: int) -> None:
        """Kiểm hạn mức rồi cộng giây ghi âm TRƯỚC khi gọi STT, một bước dưới khóa theo lớp và theo SV: tải lên song
        song không cùng lọt qua khi chỉ còn đủ cho một, tải lên lỗi sau đó vẫn bị tính. Không commit."""
        for key in sorted((f"quota:{class_id}", f"quota:{student_id}")):
            self.db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))
        self.check(student_id, class_id, audio=True)
        self.add_audio(session_id, student_id, class_id, seconds)

    def add_audio(self, session_id: UUID, student_id: UUID, class_id: UUID, seconds: int) -> None:
        """Cộng giây ghi âm vào phiên. Không commit."""
        stmt = insert(UsageRecord).values(
            session_id=session_id, student_id=student_id, class_id=class_id, tokens=0, audio_seconds=seconds
        )
        self.db.execute(
            stmt.on_conflict_do_update(
                index_elements=["session_id"],
                set_={"audio_seconds": UsageRecord.audio_seconds + stmt.excluded.audio_seconds, "updated_at": utcnow()},
            )
        )
