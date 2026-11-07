"""SessionOrchestrator – Facade điều phối Tutee / Judge / Guard (mục 4.4.3, 4.5.2). Chủ: Đăng (C1-07).

Vòng đời phiên (Hình 4.26): CREATED → EXPLAINING (gửi câu mở đầu) → CHALLENGING (lời giảng hợp lệ)
→ EVALUATING (hết vòng hỏi, Judge chấm) → COMPLETED (lưu kết quả, phát `session.completed`).
Vi phạm Guard ≥ 3 lần ⇒ FLAGGED (chờ GV xem transcript, C1-08 / GV-08).

Quy ước:
- Ma trận thành thạo chỉ đổi qua `MasteryService` (start_session / abandon); kết quả chấm đi qua sự kiện
  `session.completed` → `MasteryService.apply_result` (tiến trình `app.workers.mastery_listener`).
- Mọi lời gọi LLM đi qua `get_gateway()` (Tutee, Judge, Guard). Lời SV bọc `<student_transcript>` trong các tác tử.
- Lượt SV bị Guard chặn vẫn được lưu (GV xem lại) nhưng KHÔNG đưa vào transcript cho Tutee / Judge.
- Trạng thái phiên (câu đã hỏi, chiến lược, mục tiêu) dựng lại từ `session_turns` mỗi request – không giữ trong RAM.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.agents.guard import GuardAgent
from app.ai.agents.judge import JudgeAgent
from app.ai.agents.tutee import MAX_QUESTIONS, MIN_QUESTIONS, CoverageAnalysis, SessionContext, TuteeAgent
from app.ai.gateway import LLMGateway, get_gateway
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import tree as tree_orm
from app.models.enums import (
    FlagType,
    InputMode,
    MasteryState,
    QuestionStrategy,
    Role,
    SessionStatus,
    Speaker,
    TurnType,
    Verdict,
)
from app.models.schemas.mastery import TOPIC_SESSION_COMPLETED
from app.models.schemas.session import (
    Question,
    SessionCreated,
    SessionResult,
    SessionStart,
    Turn,
    TurnReply,
)
from app.models.schemas.tree import Node, Rubric
from app.models.session import Evaluation, SecurityFlag, SessionTurn, TeachingSession
from app.models.users import ClassSection
from app.realtime.bus import get_bus
from app.realtime.gateway import broadcast, channel_session
from app.services.mastery import MasteryService
from app.services.skill_tree import SkillTreeService

log = logging.getLogger(__name__)

ACTIVE = frozenset({SessionStatus.EXPLAINING, SessionStatus.CHALLENGING})
MAX_VIOLATIONS = 3  # Hình 4.26: vi phạm ≥ 3 lần ⇒ FLAGGED
TIMEOUT_TEXT = "(hết giờ – chưa trả lời)"
STRATEGY_COL_LEN = 24  # session_turns.strategy String(24)


# --- mã hóa (chiến lược, mục tiêu) vào cột strategy -----------------------------------------------
# TODO(Long): thêm cột session_turns.target_point_id; tạm ghép "STRATEGY|TARGET", rút gọn tên khi cần.
_STRATEGY_ALIASES = {
    "M": QuestionStrategy.MISSING_KEY_POINT,
    "P": QuestionStrategy.MISCONCEPTION_PROBE,
    "E": QuestionStrategy.EDGE_CASE,
    "T": QuestionStrategy.TRANSFER,
}


def encode_strategy(strategy: QuestionStrategy | None, target: str | None) -> str | None:
    if strategy is None:
        return None
    packed = f"{strategy.value}|{target}" if target else strategy.value
    if len(packed) > STRATEGY_COL_LEN:
        name = next(k for k, v in _STRATEGY_ALIASES.items() if v == strategy)
        packed = f"{name}|{target}"
        if len(packed) > STRATEGY_COL_LEN:
            raise AppError(
                500,
                "STRATEGY_TARGET_TOO_LONG",
                "mục tiêu quá dài cho cột strategy",
                {"length": len(packed), "limit": STRATEGY_COL_LEN},
            )
    return packed


def decode_strategy(value: str | None) -> tuple[QuestionStrategy | None, str | None]:
    if not value:
        return None, None
    name, _, target = value.partition("|")
    strategy = _STRATEGY_ALIASES.get(name)
    return (strategy if strategy is not None else QuestionStrategy(name)), (target or None)


# --- dựng lại trạng thái phiên từ session_turns ----------------------------------------------------


@dataclass
class _History:
    turns: list[SessionTurn]

    def _blocked(self, i: int) -> bool:
        """Lượt SV ngay sau đó có thông báo của hệ thống ⇒ lượt bị Guard chặn."""
        nxt = self.turns[i + 1] if i + 1 < len(self.turns) else None
        return (
            nxt is not None
            and nxt.speaker == Speaker.TUTEE
            and nxt.turn_type == TurnType.SYSTEM_NOTICE
            and self.turns[i].speaker == Speaker.STUDENT
        )

    def transcript(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for i, t in enumerate(self.turns):
            if t.turn_type == TurnType.SYSTEM_NOTICE and t.speaker == Speaker.TUTEE:
                continue
            if self._blocked(i):
                continue
            out.append({"role": "student" if t.speaker == Speaker.STUDENT else "tutee", "text": t.content or ""})
        return out

    def asked(self) -> list[Question]:
        qs = []
        for t in self.turns:
            if t.speaker == Speaker.TUTEE and t.turn_type == TurnType.QUESTION:
                strategy, target = decode_strategy(t.strategy)
                qs.append(Question(text=t.content or "…", strategy=strategy, target_point_id=target))
        return qs

    def current_question(self) -> Question | None:
        for t in reversed(self.turns):
            if t.speaker == Speaker.TUTEE and t.turn_type in (TurnType.OPENING, TurnType.QUESTION):
                strategy, target = decode_strategy(t.strategy)
                return Question(text=t.content or "…", strategy=strategy, target_point_id=target)
        return None

    def violations(self) -> int:
        return sum(1 for t in self.turns if t.speaker == Speaker.TUTEE and t.turn_type == TurnType.SYSTEM_NOTICE)

    def next_no(self) -> int:
        return (self.turns[-1].turn_no if self.turns else 0) + 1


class SessionOrchestrator:
    def __init__(
        self,
        db: Session,
        *,
        gateway: LLMGateway | None = None,
        max_questions: int = 4,
        judge_runs: int = 2,
    ) -> None:
        self.db = db
        self.gateway = gateway or get_gateway()
        self.guard = GuardAgent(self.gateway)
        self.tutee = TuteeAgent(self.gateway, max_questions=max_questions, guard=self.guard)
        self.judge = JudgeAgent(self.gateway, runs=judge_runs)
        self.max_questions = max(MIN_QUESTIONS, min(MAX_QUESTIONS, max_questions))  # FR-TB-08: 3–5 câu

    @staticmethod
    def _audio_url(s: TeachingSession, turn: SessionTurn) -> str | None:
        if not s.tts_enabled:
            return None
        return f"{get_settings().api_prefix}/sessions/{s.id}/turns/{turn.turn_no}/tts"

    def _current_question(self, s: TeachingSession, h: _History) -> Question | None:
        q = h.current_question()
        if q is not None:
            turn = next(
                t
                for t in reversed(h.turns)
                if t.speaker == Speaker.TUTEE and t.turn_type in (TurnType.OPENING, TurnType.QUESTION)
            )
            q.audio_url = self._audio_url(s, turn)
        return q

    # ------------------------------------------------------------------ nạp dữ liệu

    def _node(self, node_id: UUID) -> tuple[UUID, Node]:
        """(class_id, Node kèm rubric) của nút. TODO(Long): SkillTreeService nên có hàm công khai cho việc này."""
        n = self.db.get(tree_orm.ConceptNode, node_id)
        if n is None:
            raise AppError(404, "NODE_NOT_FOUND", "Không tìm thấy nút", {"nodeId": str(node_id)})
        tv = SkillTreeService(self.db).version_schema(n.version_id)
        node = next((x for x in tv.nodes if x.id == node_id), None)
        if node is None:
            raise AppError(404, "NODE_NOT_FOUND", "Không tìm thấy nút", {"nodeId": str(node_id)})
        return tv.class_id, node

    def _session(self, session_id: UUID, user_id: UUID, *, lock: bool = False) -> TeachingSession:
        q = select(TeachingSession).where(TeachingSession.id == session_id)
        if lock:
            q = q.with_for_update()
        s = self.db.scalar(q.execution_options(populate_existing=True))
        if s is None:
            raise AppError(404, "SESSION_NOT_FOUND", "Không tìm thấy phiên", {"sessionId": str(session_id)})
        if s.student_id != user_id:
            raise AppError(403, "FORBIDDEN", "Đây không phải phiên của bạn")
        return s

    def _active(self, session_id: UUID, user_id: UUID) -> TeachingSession:
        s = self._session(session_id, user_id, lock=True)
        if s.status not in ACTIVE:
            raise AppError(409, "SESSION_NOT_ACTIVE", "Phiên đã kết thúc", {"status": s.status})
        return s

    def _history(self, session_id: UUID) -> _History:
        rows = self.db.scalars(
            select(SessionTurn).where(SessionTurn.session_id == session_id).order_by(SessionTurn.turn_no)
        )
        return _History(list(rows))

    def _add_turn(self, s: TeachingSession, h: _History, **fields: Any) -> SessionTurn:
        t = SessionTurn(session_id=s.id, turn_no=h.next_no(), **fields)
        self.db.add(t)
        self.db.flush()
        h.turns.append(t)
        return t

    def _add_tutee(self, s: TeachingSession, h: _History, q: Question, turn_type: TurnType) -> SessionTurn:
        return self._add_turn(
            s,
            h,
            speaker=Speaker.TUTEE,
            turn_type=turn_type,
            content=q.text,
            input_mode=InputMode.TEXT,
            strategy=encode_strategy(q.strategy, q.target_point_id),
        )

    # ------------------------------------------------------------------ POST /sessions

    def start_session(self, student_id: UUID, body: SessionStart) -> SessionCreated:
        class_id, node = self._node(body.node_id)
        attempt = self.db.scalar(
            select(func.count())
            .select_from(TeachingSession)
            .where(
                TeachingSession.student_id == student_id,
                TeachingSession.node_id == body.node_id,
                TeachingSession.status == SessionStatus.COMPLETED,
            )
        )
        s = TeachingSession(
            student_id=student_id,
            node_id=body.node_id,
            class_id=class_id,
            input_mode=body.input_mode,
            status=SessionStatus.CREATED,
            attempt_no=(attempt or 0) + 1,
            is_peer_followup=body.peer_match_item_id is not None,
            peer_match_item_id=body.peer_match_item_id,
            tts_enabled=body.tts_enabled,
        )
        self.db.add(s)
        self.db.flush()
        mastery = MasteryService(self.db)
        try:
            mastery.start_session(student_id, body.node_id, s.id)  # commit cả TeachingSession
        except AppError as exc:
            self.db.rollback()
            raise _start_error(exc, body.node_id) from exc

        try:
            opening = self.tutee.opening_line(node, session_id=str(s.id))
            h = _History([])
            opening_turn = self._add_tutee(s, h, opening, TurnType.OPENING)
            opening.audio_url = self._audio_url(s, opening_turn)
            s.status = SessionStatus.EXPLAINING
            self.db.commit()
        except Exception:
            # Chưa gửi được câu mở đầu ⇒ trả ô về trạng thái trước phiên, phiên tính là bỏ dở.
            self.db.rollback()
            s = self.db.get(TeachingSession, s.id)
            s.status = SessionStatus.ABANDONED
            s.ended_at = datetime.now(UTC)
            mastery.abandon(student_id, body.node_id, s.id)  # commit
            raise
        self._emit_question(s.id, opening)
        return SessionCreated(session_id=s.id, status=SessionStatus.EXPLAINING, opening=opening)

    # ------------------------------------------------------------------ POST /sessions/{id}/turns

    def handle_turn(self, student_id: UUID, session_id: UUID, turn: Turn) -> TurnReply:
        s = self._active(session_id, student_id)
        _, node = self._node(s.node_id)
        h = self._history(s.id)
        explaining = s.status == SessionStatus.EXPLAINING
        turn_type = TurnType.EXPLANATION if explaining else TurnType.ANSWER

        try:
            # C1-08: số liệu dán / tốc độ gõ chỉ có nghĩa với lượt gõ phím; lượt giọng nói do STT sinh chữ.
            typed = turn.input_mode == InputMode.TEXT
            g = self.guard.check_input(
                turn.text,
                node.title,
                turn.paste_ratio if typed else None,
                typing_cps=turn.typing_cps if typed else None,
                session_id=str(s.id),
            )
            student_turn = self._add_turn(
                s,
                h,
                speaker=Speaker.STUDENT,
                turn_type=turn_type,
                content=turn.text,
                input_mode=turn.input_mode,
                audio_url=turn.audio_ref,
                stt_confidence=turn.stt_confidence,
                transcript_edited=turn.transcript_edited,
                paste_ratio=turn.paste_ratio,
                response_time_ms=turn.response_time_ms,
            )
            for flag in g.flags:
                paste = flag == FlagType.PASTE_SUSPECTED  # chỉ đánh dấu, không chặn ⇒ luôn LOW
                self.db.add(
                    SecurityFlag(
                        session_id=s.id,
                        turn_id=student_turn.id,
                        type=flag,
                        severity="HIGH" if g.blocked and not paste else "LOW",
                        # TODO(Long): session_turns chưa có cột typing_cps – tạm giữ số liệu trong detail của cờ.
                        detail=(g.paste_evidence if paste else g.evidence) or None,
                    )
                )
            if g.blocked:
                return self._blocked(s, h, g.notice or "", g.flags)

            if explaining:
                s.status = SessionStatus.CHALLENGING
            reply = self._advance(s, h, node, flags=g.flags)
        except Exception:
            self.db.rollback()
            raise
        return reply

    def _blocked(self, s: TeachingSession, h: _History, notice: str, flags: list[FlagType]) -> TurnReply:
        """Guard chặn: lưu thông báo trung lập, hỏi lại câu đang hỏi; quá MAX_VIOLATIONS ⇒ FLAGGED."""
        self._add_turn(
            s, h, speaker=Speaker.TUTEE, turn_type=TurnType.SYSTEM_NOTICE, content=notice, input_mode=InputMode.TEXT
        )
        asked = len(h.asked())
        if h.violations() >= MAX_VIOLATIONS:
            s.status = SessionStatus.FLAGGED
            s.ended_at = datetime.now(UTC)
            # Phiên dừng chờ GV; ô ma trận trả về trạng thái trước phiên để SV không bị kẹt IN_PROGRESS.
            # abandon commit cả phiên và ô ma trận; lỗi trước commit thì handle_turn rollback được cả hai.
            MasteryService(self.db).abandon(s.student_id, s.node_id, s.id)
            return TurnReply(
                status=SessionStatus.FLAGGED,
                question=None,
                notice=notice,
                questions_asked=asked,
                questions_total=max(asked, self.max_questions),
                flags=flags,
            )
        self.db.commit()
        return TurnReply(
            status=SessionStatus(s.status),
            question=self._current_question(s, h),
            notice=notice,
            questions_asked=asked,
            questions_total=max(asked, self.max_questions),
            flags=flags,
        )

    # ------------------------------------------------------------------ POST /sessions/{id}/timeout

    def handle_timeout(self, student_id: UUID, session_id: UUID) -> TurnReply:
        """Câu hiện tại tính là chưa trả lời, sang câu kế (FR-TB-11). Đồng hồ / hạn theo lớp: C1-15."""
        s = self._active(session_id, student_id)
        _, node = self._node(s.node_id)
        h = self._history(s.id)
        try:
            self._add_turn(
                s,
                h,
                speaker=Speaker.STUDENT,
                turn_type=TurnType.SYSTEM_NOTICE,
                content=TIMEOUT_TEXT,
                input_mode=InputMode.TEXT,
            )
            if s.status == SessionStatus.EXPLAINING:
                s.status = SessionStatus.CHALLENGING
            reply = self._advance(s, h, node, flags=[])
        except Exception:
            self.db.rollback()
            raise
        return reply

    # ------------------------------------------------------------------ vòng phản biện / chấm

    def _advance(self, s: TeachingSession, h: _History, node: Node, *, flags: list[FlagType]) -> TurnReply:
        """Phân tích độ bao phủ → câu hỏi kế (Hình 4.28); hết câu ⇒ chấm và hoàn tất."""
        transcript = h.transcript()
        coverage = self._coverage(transcript, node, str(s.id))
        ctx = SessionContext(
            node=node,
            transcript=transcript,
            coverage=coverage,
            asked=h.asked(),
            max_questions=self.max_questions,
            session_id=str(s.id),
        )
        question = self.tutee.next_question(ctx)
        if question is not None:
            question_turn = self._add_tutee(s, h, question, TurnType.QUESTION)
            question.audio_url = self._audio_url(s, question_turn)
            self.db.commit()
            self._emit_question(s.id, question)
            asked = len(h.asked())
            return TurnReply(
                status=SessionStatus(s.status),
                question=question,
                questions_asked=asked,
                questions_total=max(asked, self.max_questions),
                flags=flags,
            )
        self._finish(s, h, node)
        asked = len(h.asked())
        return TurnReply(
            status=SessionStatus.COMPLETED,
            question=None,
            questions_asked=asked,
            questions_total=asked,
            flags=flags,
        )

    def _coverage(self, transcript: list[dict[str, Any]], node: Node, session_id: str) -> CoverageAnalysis:
        student_only = [t for t in transcript if t["role"] == "student"]
        if not student_only or node.rubric is None:
            return CoverageAnalysis()
        return self.tutee.analyze_coverage(student_only, node, session_id=session_id)

    def _finish(self, s: TeachingSession, h: _History, node: Node) -> SessionResult:
        s.status = SessionStatus.EVALUATING
        rubric = node.rubric or Rubric(key_points=[])
        asked = h.asked()
        outcome = self.judge.evaluate(
            h.transcript(),
            rubric,
            node.title,
            challenges_total=len(asked),
            session_id=str(s.id),
        )
        flags = sorted(
            {
                FlagType(t)
                for t in self.db.scalars(select(SecurityFlag.type).where(SecurityFlag.session_id == s.id))
                if t in FlagType.__members__
            }
        )
        now = datetime.now(UTC)
        result = SessionResult(
            session_id=s.id,
            student_id=s.student_id,
            node_id=s.node_id,
            class_id=s.class_id,
            state=MasteryState.MASTERED if outcome.verdict == Verdict.PASSED else MasteryState.NOT_PASSED,
            verdict=outcome.verdict,
            total_score=outcome.total_score,
            pass_threshold=outcome.pass_check.pass_threshold,
            criteria=outcome.criteria,
            strengths=outcome.strengths,
            review_hints=outcome.review_hints,
            source_pages=outcome.source_pages,
            unlocked_nodes=[],
            flags=flags,
            is_peer_followup=s.is_peer_followup,
            detected_misconceptions=[m.id for m in outcome.result.misconceptions],
            failed_conditions=outcome.pass_check.failed_conditions,
            attempt_no=s.attempt_no,
            completed_at=now,
        )
        self.db.add(
            Evaluation(
                session_id=s.id,
                total_score=result.total_score,
                verdict=result.verdict,
                covered_points=outcome.result.covered_points,
                missing_points=outcome.result.missing_points,
                detected_misconceptions=result.detected_misconceptions,
                # TODO(Long): cột JSONB riêng cho kết quả hiển thị; tạm lưu ảnh chụp SessionResult (đã lọc lộ đáp án).
                feedback=result.model_dump_json(by_alias=True),
                judge_runs=outcome.result.judge_runs,
            )
        )
        s.status = SessionStatus.COMPLETED
        s.ended_at = now
        self.db.commit()
        try:
            get_bus().publish(TOPIC_SESSION_COMPLETED, result)
        except (RedisError, OSError):
            # Kết quả đã lưu; Pub/Sub không lưu tin ⇒ ô ma trận còn IN_PROGRESS, reconcile_completed phát lại sau.
            log.exception(
                "không phát được session.completed: phiên %s, SV %s, nút %s, %s %.1f điểm",
                s.id,
                s.student_id,
                s.node_id,
                result.verdict,
                result.total_score,
            )
        return result

    # ------------------------------------------------------------------ GET /sessions/{id}/turns/{n}/tts (C1-14)

    def question_text_for_tts(self, student_id: UUID, session_id: UUID, turn_no: int) -> str:
        """Only the session owner can play Tutee opening/question turns with TTS enabled."""
        s = self._session(session_id, student_id)
        if not s.tts_enabled:
            raise AppError(404, "TTS_NOT_ENABLED", "TTS is disabled for this session")
        t = self.db.scalar(
            select(SessionTurn).where(
                SessionTurn.session_id == s.id,
                SessionTurn.turn_no == turn_no,
                SessionTurn.speaker == Speaker.TUTEE,
                SessionTurn.turn_type.in_([TurnType.OPENING, TurnType.QUESTION]),
            )
        )
        if t is None:
            raise AppError(404, "TURN_NOT_FOUND", "No question at this turn", {"turnNo": turn_no})
        return t.content or ""

    # ------------------------------------------------------------------ POST /sessions/{id}/audio (C1-12)

    def audio_node(self, student_id: UUID, session_id: UUID) -> Node:
        """Glossary source for an active session owned by the requesting student."""
        s = self._session(session_id, student_id)
        if s.status not in ACTIVE:
            raise AppError(409, "SESSION_NOT_ACTIVE", "Phiên đã kết thúc", {"status": s.status})
        return self._node(s.node_id)[1]

    # ------------------------------------------------------------------ GET /sessions/{id}/result

    def get_result(self, user_id: UUID, role: Role, session_id: UUID) -> SessionResult:
        s = self.db.get(TeachingSession, session_id)
        if s is None:
            raise AppError(404, "SESSION_NOT_FOUND", "Không tìm thấy phiên", {"sessionId": str(session_id)})
        if role == Role.STUDENT and s.student_id != user_id:
            raise AppError(403, "FORBIDDEN", "Đây không phải phiên của bạn")
        if role == Role.LECTURER:
            cls = self.db.get(ClassSection, s.class_id)  # TODO(Long): hàm kiểm GV chủ lớp dùng chung
            if cls is None or cls.lecturer_id != user_id:
                raise AppError(403, "FORBIDDEN", "Phiên không thuộc lớp của bạn")
        if s.status != SessionStatus.COMPLETED:
            raise AppError(409, "RESULT_NOT_READY", "Phiên chưa chấm xong", {"status": s.status})
        ev = self.db.scalar(select(Evaluation).where(Evaluation.session_id == s.id))
        if ev is None or not ev.feedback:
            raise AppError(409, "RESULT_NOT_READY", "Phiên chưa có kết quả", {"status": s.status})
        try:
            return SessionResult.model_validate(json.loads(ev.feedback))
        except (ValueError, ValidationError) as exc:
            log.exception("ảnh chụp kết quả phiên %s không hợp lệ", s.id)
            raise AppError(500, "RESULT_CORRUPTED", "Kết quả phiên lưu không hợp lệ") from exc

    # ------------------------------------------------------------------ kênh session:{id}

    @staticmethod
    def _emit_question(session_id: UUID, q: Question) -> None:
        """Bảng 5.11: session.question {text, audioUrl?, deadline?}. Kênh WS làm ở C2-13 (Long)."""
        payload = q.model_dump(by_alias=True, mode="json", include={"text", "audio_url", "deadline"})
        try:
            broadcast(channel_session(str(session_id)), "session.question", payload)
        except NotImplementedError:
            log.debug("chưa có RealtimeGateway (C2-13) – bỏ qua session.question cho phiên %s", session_id)


RECONCILE_SETTLE = timedelta(seconds=60)  # tin phát bình thường có thể đang trên đường – chưa đụng
RECONCILE_WINDOW = timedelta(hours=24)  # chỉ đối soát phiên kết thúc gần đây


def reconcile_completed(db: Session, *, now: datetime | None = None) -> int:
    """Phát lại `session.completed` cho phiên COMPLETED mà ô ma trận vẫn IN_PROGRESS (#94).

    Pub/Sub không lưu tin: Redis / bên nghe lỗi đúng lúc `_finish` phát thì kết quả đã lưu nhưng ô kẹt IN_PROGRESS.
    Chỉ xét phiên kết thúc trong RECONCILE_WINDOW và đã quá RECONCILE_SETTLE. Phát lại an toàn vì
    `MasteryService.apply_result` bỏ qua tin của phiên mà ô đã rời IN_PROGRESS. Chạy định kỳ ở
    `app.workers.sessions`. Trả số phiên đã phát lại; Redis vẫn lỗi ⇒ dừng, lần chạy sau thử tiếp.
    """
    now = now or datetime.now(UTC)
    rows = db.execute(
        select(TeachingSession.id, Evaluation.feedback)
        .join(Evaluation, Evaluation.session_id == TeachingSession.id)
        .where(
            TeachingSession.status == SessionStatus.COMPLETED,
            TeachingSession.ended_at >= now - RECONCILE_WINDOW,
            TeachingSession.ended_at <= now - RECONCILE_SETTLE,
        )
        .order_by(TeachingSession.ended_at)
    ).all()
    if not rows:
        return 0
    mastery = MasteryService(db)
    pending = mastery.pending_results(sid for sid, _ in rows)
    db.rollback()  # chỉ đọc – không giữ giao dịch / khóa trong lúc phát
    bus = get_bus()
    sent = 0
    for sid, feedback in rows:
        if sid not in pending:
            continue
        try:
            result = SessionResult.model_validate(json.loads(feedback or ""))
        except (ValueError, ValidationError):
            log.exception("đối soát: ảnh chụp kết quả phiên %s không hợp lệ – bỏ qua", sid)
            continue
        try:
            bus.publish(TOPIC_SESSION_COMPLETED, result)
        except (RedisError, OSError):
            log.exception("đối soát: vẫn không phát được session.completed cho phiên %s – thử lại lần sau", sid)
            break
        log.warning("đối soát: đã phát lại session.completed cho phiên %s (SV %s)", sid, result.student_id)
        sent += 1
    return sent


def _start_error(exc: AppError, node_id: UUID) -> AppError:
    """Bổ sung details theo hợp đồng POST /sessions (NodeLockedDetails / NodeAlreadyMasteredDetails)."""
    if exc.code == "NODE_LOCKED":
        details = {
            "nodeId": str(node_id),
            "state": MasteryState.LOCKED.value,
            "missingPrerequisites": (exc.details or {}).get("missingPrerequisites", []),
        }
        return AppError(exc.status, exc.code, exc.message, details)
    if exc.code == "NODE_ALREADY_MASTERED":
        return AppError(
            exc.status, exc.code, exc.message, {"nodeId": str(node_id), "state": MasteryState.MASTERED.value}
        )
    return exc
