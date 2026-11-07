"""Phiên giảng lại – MX2, FR-TB-02…15. Chủ: Đăng (C1-07, C1-12, C1-15). Facade: SessionOrchestrator."""

from uuid import UUID

from fastapi import APIRouter, File, UploadFile

from app.api.deps import CurrentUser, LecturerOrStudent, Student
from app.core.errors import NotImplementedYet
from app.models.schemas.session import (
    SessionCreated,
    SessionResult,
    SessionStart,
    Transcript,
    Turn,
    TurnReply,
)

router = APIRouter(tags=["sessions"])


@router.post("/sessions", response_model=SessionCreated, status_code=201)
def start_session(body: SessionStart, user: CurrentUser = Student) -> SessionCreated:
    """Chỉ cho bắt đầu ở nút AVAILABLE / NOT_PASSED (hết chờ BR-11) / NEEDS_REVERIFY;
    nút khóa ⇒ 409 NODE_LOCKED kèm tiên quyết còn thiếu (TC06)."""
    raise NotImplementedYet("C1-07")


@router.post("/sessions/{session_id}/audio", response_model=Transcript)
def upload_audio(session_id: UUID, file: UploadFile = File(...), user: CurrentUser = Student) -> Transcript:
    """Ghi âm ≤ 3 phút → STT tiếng Việt, chuẩn hóa thuật ngữ, độ tin cậy từng từ (FR-TB-05…07)."""
    raise NotImplementedYet("C1-12")


@router.post("/sessions/{session_id}/turns", response_model=TurnReply)
def post_turn(session_id: UUID, body: Turn, user: CurrentUser = Student) -> TurnReply:
    """Guard đầu vào → lưu lượt → Tutee chọn chiến lược và hỏi (Guard đầu ra)."""
    raise NotImplementedYet("C1-07")


@router.post("/sessions/{session_id}/timeout", response_model=TurnReply)
def timeout(session_id: UUID, user: CurrentUser = Student) -> TurnReply:
    """Hết giờ trả lời một câu (FR-TB-11)."""
    raise NotImplementedYet("C1-15")


@router.get("/sessions/{session_id}/result", response_model=SessionResult)
def get_result(session_id: UUID, user: CurrentUser = LecturerOrStudent) -> SessionResult:
    """SV chỉ xem của mình, GV xem SV lớp mình (TC16 ⇒ 403)."""
    raise NotImplementedYet("C1-07")


@router.get("/me/sessions", response_model=list[SessionResult])
def my_sessions(class_id: UUID | None = None, user: CurrentUser = Student) -> list[SessionResult]:
    """SV-08 Lịch sử phiên (FR-TB-15, vòng 3)."""
    raise NotImplementedYet("C2-20")
