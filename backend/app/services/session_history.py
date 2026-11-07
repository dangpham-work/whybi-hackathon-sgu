"""Lịch sử phiên, hồ sơ năng lực SV, nghe lại ghi âm và dọn ghi âm quá hạn. Chủ: Long (C2-17, C2-20).

Chỉ ĐỌC bảng phiên của Orchestrator (teaching_sessions, session_turns, evaluations); kết quả chấm lấy từ ảnh chụp
`SessionResult` mà Orchestrator đã lưu ở `evaluations.feedback`, nên không tự tính lại điểm.
Ghi âm (NFR-09, BR-13): chỉ lưu khi SV đồng ý, tự xóa sau `AUDIO_RETENTION_DAYS` ngày; transcript giữ nguyên.
"""

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.enums import MasteryState, Role, SessionStatus, Verdict
from app.models.schemas.heatmap import ProfileSession, ProfileTurn, StudentProfile
from app.models.schemas.session import SessionResult
from app.models.session import Evaluation, SessionTurn, TeachingSession
from app.services.auth import student_identities
from app.services.classes import ClassService
from app.services.mastery import MasteryService
from app.services.skill_tree import SkillTreeService
from app.services.storage import StorageUnavailable, default_storage

if TYPE_CHECKING:
    from app.api.deps import CurrentUser

log = logging.getLogger(__name__)

AUDIO_SCHEME = "s3://audio/"  # speech.py lưu audio_ref = "s3://" + khóa "audio/<phiên>/<uuid>.<đuôi>"
AUDIO_TYPES = {"webm": "audio/webm", "ogg": "audio/ogg", "wav": "audio/wav", "mp3": "audio/mpeg", "m4a": "audio/mp4"}


_AUDIO_KEY = re.compile(r"audio/(?P<session>[0-9a-f-]{36})/[0-9a-f-]{36}\.(?:webm|ogg|wav|mp3|m4a)")


def audio_key(audio_url: str | None, session_id: UUID) -> str | None:
    """Khóa đối tượng ghi âm của chính phiên này, hoặc None.

    `audio_url` do client gửi lên (`audioRef` trong lượt) nên KHÔNG tin: chỉ nhận đúng dạng SpeechService tạo ra
    `s3://audio/<session_id>/<uuid>.<đuôi>` và phải khớp phiên của lượt – chặn đọc / xóa đối tượng khác trong bucket
    (ghi âm phiên khác, giáo trình, `..`)."""
    if not audio_url or not audio_url.startswith("s3://"):
        return None
    key = audio_url.removeprefix("s3://")
    m = _AUDIO_KEY.fullmatch(key)
    return key if m and m["session"] == str(session_id) else None


def _storage_url(key: str) -> str:
    return f"s3://{get_settings().s3_bucket}/{key}"


def audio_endpoint(turn_id: UUID) -> str:
    return f"/api/v1/turns/{turn_id}/audio"


class SessionHistoryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ hồ sơ SV (GV-07 / GV-08)

    def _results(self, session_ids: list[UUID]) -> dict[UUID, SessionResult]:
        out: dict[UUID, SessionResult] = {}
        rows = self.db.execute(
            select(Evaluation.session_id, Evaluation.feedback).where(Evaluation.session_id.in_(session_ids))
        )
        for sid, feedback in rows:
            try:
                out[sid] = SessionResult.model_validate(json.loads(feedback))
            except (TypeError, ValueError, ValidationError):
                log.warning("ảnh chụp kết quả phiên %s không đọc được – bỏ qua", sid)
        return out

    def student_profile(self, class_id: UUID, student_id: UUID, user: "CurrentUser") -> StudentProfile:
        """Tiến độ từng nút + mọi phiên (kèm transcript, ghi âm) của SV trong lớp. Chỉ GV phụ trách lớp."""
        if user.role != Role.LECTURER or ClassService(self.db).lecturer_id(class_id) != user.id:
            raise AppError(403, "NOT_CLASS_OWNER", "Chỉ GV phụ trách lớp được xem hồ sơ SV")
        my_map = MasteryService(self.db).my_map(class_id, student_id)  # 403 NOT_ENROLLED nếu SV không ở lớp
        titles = {n.key: n.title for n in my_map.tree.nodes}
        name, code = student_identities(self.db, [student_id]).get(student_id, ("", ""))

        sessions = list(
            self.db.scalars(
                select(TeachingSession)
                .where(TeachingSession.student_id == student_id, TeachingSession.class_id == class_id)
                .order_by(TeachingSession.started_at.desc())
            )
        )
        return StudentProfile(
            class_id=class_id,
            student_id=student_id,
            full_name=name,
            student_code=code,
            mastered_count=my_map.mastered_count,
            total_count=my_map.total_count,
            progress=my_map.progress,
            sessions=self._sessions_out(sessions, titles),
        )

    def _sessions_out(self, sessions: list[TeachingSession], titles: dict[str, str]) -> list[ProfileSession]:
        """Phiên kèm kết quả chấm và transcript; `titles` tra tên nút theo key (nút phiên bản cũ có thể không có)."""
        ids = [s.id for s in sessions]
        keys = SkillTreeService(self.db).node_keys([s.node_id for s in sessions])
        results = self._results(ids)
        turns: dict[UUID, list[ProfileTurn]] = {}
        q = (
            select(SessionTurn)
            .where(SessionTurn.session_id.in_(ids))
            .order_by(SessionTurn.session_id, SessionTurn.turn_no)
        )
        for t in self.db.scalars(q):
            turns.setdefault(t.session_id, []).append(
                ProfileTurn(
                    turn_no=t.turn_no,
                    speaker=t.speaker,
                    turn_type=t.turn_type,
                    content=t.content,
                    input_mode=t.input_mode,
                    audio_url=audio_endpoint(t.id) if audio_key(t.audio_url, t.session_id) else None,
                    created_at=t.created_at,
                )
            )
        return [
            ProfileSession(
                session_id=s.id,
                node_id=s.node_id,
                node_key=keys.get(s.node_id),
                node_title=titles.get(keys.get(s.node_id, "")),
                attempt_no=s.attempt_no,
                status=s.status,
                started_at=s.started_at,
                ended_at=s.ended_at,
                result=results.get(s.id) if s.status == SessionStatus.COMPLETED else None,
                turns=turns.get(s.id, []),
            )
            for s in sessions
        ]

    # ------------------------------------------------------------------ lịch sử phiên của SV (SV-08, FR-TB-15)

    def my_sessions(self, student_id: UUID, class_id: UUID | None) -> list[SessionResult]:
        """Kết quả các phiên đã chấm xong của chính SV, mới nhất trước. Thiếu ảnh chụp kết quả đầy đủ thì dựng bản
        tối thiểu từ điểm và kết luận đã lưu để phiên không biến mất khỏi lịch sử."""
        q = (
            select(TeachingSession, Evaluation)
            .join(Evaluation, Evaluation.session_id == TeachingSession.id)
            .where(TeachingSession.student_id == student_id, TeachingSession.status == SessionStatus.COMPLETED)
            .order_by(TeachingSession.started_at.desc())
        )
        if class_id is not None:
            q = q.where(TeachingSession.class_id == class_id)
        out: list[SessionResult] = []
        for s, ev in self.db.execute(q):
            try:
                out.append(SessionResult.model_validate(json.loads(ev.feedback)))
                continue
            except (TypeError, ValueError, ValidationError):
                pass
            passed = ev.verdict == Verdict.PASSED
            out.append(
                SessionResult(
                    session_id=s.id,
                    student_id=s.student_id,
                    node_id=s.node_id,
                    class_id=s.class_id,
                    state=MasteryState.MASTERED if passed else MasteryState.NOT_PASSED,
                    verdict=Verdict(ev.verdict),
                    total_score=float(ev.total_score),
                    criteria=[],
                    attempt_no=s.attempt_no,
                    completed_at=s.ended_at,
                )
            )
        return out

    def my_session(self, student_id: UUID, session_id: UUID) -> ProfileSession:
        """Một phiên của chính SV kèm transcript và đường dẫn nghe lại ghi âm (còn hạn). Phiên người khác ⇒ 403."""
        s = self.db.get(TeachingSession, session_id)
        if s is None:
            raise AppError(404, "SESSION_NOT_FOUND", "Không tìm thấy phiên", {"sessionId": str(session_id)})
        if s.student_id != student_id:
            raise AppError(403, "FORBIDDEN", "Đây không phải phiên của bạn")
        _, node = SkillTreeService(self.db).get_node_for_session(s.node_id)
        return self._sessions_out([s], {node.key: node.title})[0]

    # ------------------------------------------------------------------ nghe lại ghi âm

    def audio_for_turn(self, turn_id: UUID, user: "CurrentUser") -> tuple[bytes, str]:
        """Nội dung ghi âm một lượt: chính SV chủ phiên hoặc GV phụ trách lớp. Hết hạn / không ghi âm ⇒ 404."""
        row = self.db.execute(
            select(SessionTurn.audio_url, SessionTurn.session_id, TeachingSession.student_id, TeachingSession.class_id)
            .join(TeachingSession, TeachingSession.id == SessionTurn.session_id)
            .where(SessionTurn.id == turn_id)
        ).first()
        if row is None:
            raise AppError(404, "TURN_NOT_FOUND", "Không tìm thấy lượt hội thoại")
        audio_url, session_id, student_id, class_id = row
        allowed = (user.role == Role.STUDENT and user.id == student_id) or (
            user.role == Role.LECTURER and ClassService(self.db).lecturer_id(class_id) == user.id
        )
        if not allowed:
            raise AppError(403, "FORBIDDEN", "Bạn không được nghe ghi âm này")
        key = audio_key(audio_url, session_id)
        if key is None:
            raise AppError(404, "AUDIO_NOT_AVAILABLE", "Lượt này không có ghi âm (không được lưu hoặc đã quá hạn)")
        try:
            data = default_storage().get(_storage_url(key))
        except KeyError:  # đối tượng đã bị lifecycle của MinIO xóa trước khi beat dọn kịp cập nhật CSDL
            raise AppError(404, "AUDIO_NOT_AVAILABLE", "Ghi âm đã quá hạn lưu") from None
        except StorageUnavailable as e:
            raise AppError(503, "AUDIO_STORE_UNAVAILABLE", "Kho ghi âm tạm lỗi, thử lại sau") from e
        return data, AUDIO_TYPES.get(audio_url.rsplit(".", 1)[-1], "application/octet-stream")


def purge_expired_audio(db: Session, now: datetime | None = None) -> int:
    """NFR-09: xóa ghi âm quá `audio_retention_days` ngày – xóa đối tượng rồi đặt `audio_url = NULL`
    (transcript giữ). Kho lỗi ⇒ giữ nguyên dòng đó để lần chạy sau thử lại. Trả số ghi âm đã xóa."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=get_settings().audio_retention_days)
    storage = default_storage()
    turns = db.scalars(
        select(SessionTurn).where(SessionTurn.audio_url.like(f"{AUDIO_SCHEME}%"), SessionTurn.created_at < cutoff)
    ).all()
    purged = 0
    for t in turns:
        key = audio_key(t.audio_url, t.session_id)
        if key is not None:  # tham chiếu lạ (client gửi) thì chỉ gỡ khỏi dòng, không đụng đối tượng nào
            try:
                storage.remove(_storage_url(key))
            except StorageUnavailable:
                log.exception("không xóa được ghi âm của lượt %s – thử lại lần sau", t.id)
                continue
        t.audio_url = None
        purged += 1
    db.commit()
    return purged
