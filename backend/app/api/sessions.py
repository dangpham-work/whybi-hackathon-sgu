"""Phiên giảng lại – MX2, FR-TB-02…15. Chủ: Đăng (C1-07, C1-12, C1-15). Facade: SessionOrchestrator.

HỢP ĐỒNG (C1-07) – JSON camelCase, lỗi {"error": {code, message, details}}:
- POST /sessions (SV) body SessionStart → 201 SessionCreated (status EXPLAINING, opening = câu mở đầu Tutee).
    404 NODE_NOT_FOUND
    · 409 NODE_LOCKED, details = NodeLockedDetails {nodeId, state: LOCKED, missingPrerequisites: key[]}
    · 409 NODE_ALREADY_MASTERED, details = NodeAlreadyMasteredDetails {nodeId, state: MASTERED} (mã C2-10)
    (chỉ bắt đầu khi ô ở AVAILABLE / NOT_PASSED / NEEDS_REVERIFY).
- POST /sessions/{id}/turns (SV chủ phiên) body Turn → 200 TurnReply.
    Lượt đầu là lời giảng, sau đó là câu trả lời.
    Guard chặn ⇒ question = câu đang hỏi (hỏi lại), kèm notice trung lập và flags.
    question = null ⇒ vòng phản biện xong, đã chấm; gọi GET /result.
    404 SESSION_NOT_FOUND · 403 FORBIDDEN (phiên của SV khác) · 409 SESSION_NOT_ACTIVE {status}.
- POST /sessions/{id}/timeout (SV chủ phiên) → 200 TurnReply: câu hiện tại tính là chưa trả lời, sang câu kế.
    Lỗi như /turns.
- GET /sessions/{id}/result (SV chủ phiên, GV) → 200 SessionResult.
    404 SESSION_NOT_FOUND · 403 FORBIDDEN · 409 RESULT_NOT_READY {status}.
- Kênh WebSocket session:{id}: sự kiện session.question {text, audioUrl?, deadline?} (Bảng 5.11).
- Sự kiện nội bộ session.completed (Redis Pub/Sub): payload SessionResult, phát một lần khi chấm xong.
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, LecturerOrStudent, Student
from app.core.errors import NotImplementedYet
from app.db.session import get_db
from app.models.schemas.common import ApiModel, ErrorResponse
from app.models.schemas.session import (
    NodeAlreadyMasteredDetails,
    NodeLockedDetails,
    SessionCreated,
    SessionResult,
    SessionStart,
    Transcript,
    Turn,
    TurnReply,
)
from app.services.session_orchestrator import SessionOrchestrator
from app.services.speech import MAX_AUDIO_BYTES, SpeechService, TtsService

router = APIRouter(tags=["sessions"])


def get_orchestrator(db: Session = Depends(get_db)) -> SessionOrchestrator:
    return SessionOrchestrator(db)


def get_speech_service() -> SpeechService:
    return SpeechService()


def get_tts_service() -> TtsService:
    return TtsService()


class NodeLockedErrorBody(ApiModel):
    code: Literal["NODE_LOCKED"] = "NODE_LOCKED"
    message: str
    details: NodeLockedDetails


class NodeLockedErrorResponse(ApiModel):
    error: NodeLockedErrorBody


class NodeAlreadyMasteredErrorBody(ApiModel):
    code: Literal["NODE_ALREADY_MASTERED"] = "NODE_ALREADY_MASTERED"
    message: str
    details: NodeAlreadyMasteredDetails


class NodeAlreadyMasteredErrorResponse(ApiModel):
    error: NodeAlreadyMasteredErrorBody


_SESSION_ERRORS = {
    403: {"model": ErrorResponse, "description": "FORBIDDEN – phiên của sinh viên khác"},
    404: {"model": ErrorResponse, "description": "SESSION_NOT_FOUND"},
    409: {"model": ErrorResponse, "description": "SESSION_NOT_ACTIVE – phiên đã kết thúc"},
}


@router.post(
    "/sessions",
    response_model=SessionCreated,
    status_code=201,
    responses={
        404: {"model": ErrorResponse, "description": "NODE_NOT_FOUND"},
        409: {
            "model": NodeLockedErrorResponse | NodeAlreadyMasteredErrorResponse,
            "description": "NODE_LOCKED – tiên quyết còn thiếu · NODE_ALREADY_MASTERED – nút đã Đạt",
        },
    },
)
def start_session(
    body: SessionStart,
    user: CurrentUser = Student,
    orch: SessionOrchestrator = Depends(get_orchestrator),
) -> SessionCreated:
    """Chỉ cho bắt đầu ở nút AVAILABLE / NOT_PASSED (hết chờ BR-11) / NEEDS_REVERIFY;
    nút khóa ⇒ 409 NODE_LOCKED kèm tiên quyết còn thiếu (TC06)."""
    return orch.start_session(user.id, body)


@router.post("/sessions/{session_id}/audio", response_model=Transcript, responses=_SESSION_ERRORS)
def upload_audio(
    session_id: UUID,
    file: UploadFile = File(...),
    consent: bool = Form(False),
    user: CurrentUser = Student,
    orch: SessionOrchestrator = Depends(get_orchestrator),
    speech: SpeechService = Depends(get_speech_service),
) -> Transcript:
    """Transcribe the owner's active session; save recording only with consent (BR-13)."""
    node = orch.audio_node(user.id, session_id)
    audio = file.file.read(MAX_AUDIO_BYTES + 1)
    return speech.transcribe(audio, node, session_id=session_id, consent=consent)


@router.get(
    "/sessions/{session_id}/turns/{turn_no}/tts",
    responses={
        200: {"content": {"audio/mpeg": {}, "audio/wav": {}}, "description": "Question audio"},
        403: _SESSION_ERRORS[403],
        404: {"model": ErrorResponse, "description": "SESSION_NOT_FOUND / TTS_NOT_ENABLED / TURN_NOT_FOUND"},
        503: {"model": ErrorResponse, "description": "TTS_UNAVAILABLE"},
    },
)
def question_audio(
    session_id: UUID,
    turn_no: int,
    user: CurrentUser = Student,
    orch: SessionOrchestrator = Depends(get_orchestrator),
    tts: TtsService = Depends(get_tts_service),
) -> Response:
    """Read a question for the session owner; synthesize on first playback, then cache."""
    text = orch.question_text_for_tts(user.id, session_id, turn_no)
    audio, content_type = tts.audio_for(session_id, turn_no, text)
    return Response(audio, media_type=content_type, headers={"Cache-Control": "private, max-age=3600"})


@router.post("/sessions/{session_id}/turns", response_model=TurnReply, responses=_SESSION_ERRORS)
def post_turn(
    session_id: UUID,
    body: Turn,
    user: CurrentUser = Student,
    orch: SessionOrchestrator = Depends(get_orchestrator),
) -> TurnReply:
    """Guard đầu vào → lưu lượt → Tutee chọn chiến lược và hỏi (Guard đầu ra)."""
    return orch.handle_turn(user.id, session_id, body)


@router.post("/sessions/{session_id}/timeout", response_model=TurnReply, responses=_SESSION_ERRORS)
def timeout(
    session_id: UUID,
    user: CurrentUser = Student,
    orch: SessionOrchestrator = Depends(get_orchestrator),
) -> TurnReply:
    """Hết giờ trả lời một câu (FR-TB-11). Đồng hồ và hạn cấu hình theo lớp: C1-15."""
    return orch.handle_timeout(user.id, session_id)


@router.get(
    "/sessions/{session_id}/result",
    response_model=SessionResult,
    responses={**_SESSION_ERRORS, 409: {"model": ErrorResponse, "description": "RESULT_NOT_READY"}},
)
def get_result(
    session_id: UUID,
    user: CurrentUser = LecturerOrStudent,
    orch: SessionOrchestrator = Depends(get_orchestrator),
) -> SessionResult:
    """SV chỉ xem của mình, GV xem SV lớp mình (TC16 ⇒ 403)."""
    return orch.get_result(user.id, user.role, session_id)


@router.get("/me/sessions", response_model=list[SessionResult])
def my_sessions(class_id: UUID | None = None, user: CurrentUser = Student) -> list[SessionResult]:
    """SV-08 Lịch sử phiên (FR-TB-15, vòng 3)."""
    raise NotImplementedYet("C2-20")
