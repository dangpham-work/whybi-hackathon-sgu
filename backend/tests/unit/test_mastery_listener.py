"""C2-10: tiến trình nghe session.completed – đăng ký đúng chủ đề, từ chối chạy với bus trong bộ nhớ."""

import json
from unittest.mock import Mock
from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError

from app.core.errors import AppError
from app.models.enums import MasteryState, Verdict
from app.models.schemas.mastery import TOPIC_SESSION_COMPLETED, MasteryChanged
from app.models.schemas.session import SessionResult
from app.models.session import Evaluation
from app.realtime.bus import InMemoryEventBus
from app.services.mastery import MasteryService, register_handlers
from app.workers import mastery_listener


def test_register_handlers_subscribes_session_completed():
    bus = InMemoryEventBus()
    register_handlers(bus, session_factory=lambda: None)
    assert len(bus._handlers[TOPIC_SESSION_COMPLETED]) == 1


def test_listener_refuses_memory_bus():
    with pytest.raises(SystemExit):
        mastery_listener.main(InMemoryEventBus())


def test_failed_result_handler_rolls_back_closes_and_logs_context(monkeypatch, caplog):
    bus = InMemoryEventBus()
    db = Mock()
    error = AppError(404, "NODE_NOT_FOUND", "Không tìm thấy nút")
    monkeypatch.setattr(MasteryService, "apply_result", Mock(side_effect=error))
    register_handlers(bus, session_factory=lambda: db)
    event = SessionResult(
        session_id=uuid4(),
        student_id=uuid4(),
        node_id=uuid4(),
        class_id=uuid4(),
        state=MasteryState.MASTERED,
        verdict=Verdict.PASSED,
        total_score=80,
        criteria=[],
    )
    bus.publish(TOPIC_SESSION_COMPLETED, event)
    db.rollback.assert_called_once()
    db.close.assert_called_once()
    assert any(
        r.levelname == "ERROR"
        and str(event.session_id) in r.getMessage()
        and "NODE_NOT_FOUND" in r.getMessage()
        and r.exc_info
        for r in caplog.records
    )


def test_redis_publish_failure_keeps_commit_and_logs_context(caplog):
    db, bus = Mock(), Mock()
    bus.publish.side_effect = ConnectionError("Redis unavailable")
    event = MasteryChanged(
        class_id=uuid4(),
        student_id=uuid4(),
        node_id=uuid4(),
        node_key="a",
        old_state=MasteryState.IN_PROGRESS,
        new_state=MasteryState.MASTERED,
    )
    assert MasteryService(db, bus=bus)._commit([event]) == [event]
    db.commit.assert_called_once()
    db.rollback.assert_not_called()
    assert any(
        r.levelname == "ERROR" and str(event.student_id) in r.getMessage() and r.exc_info for r in caplog.records
    )


def test_on_session_completed_updates_evaluation_feedback_with_unlocked_nodes(monkeypatch):
    bus = InMemoryEventBus()
    db = Mock()
    ev = Evaluation(
        id=uuid4(),
        session_id=uuid4(),
        feedback=json.dumps({"unlockedNodes": [], "score": 85}),
    )
    db.scalar.return_value = ev

    sid = ev.session_id
    u1, u2 = uuid4(), uuid4()
    changed = MasteryChanged(
        class_id=uuid4(),
        student_id=uuid4(),
        node_id=uuid4(),
        node_key="a",
        old_state=MasteryState.IN_PROGRESS,
        new_state=MasteryState.MASTERED,
        unlocked_node_ids=[u1, u2],
    )
    monkeypatch.setattr(MasteryService, "apply_result", Mock(return_value=changed))

    register_handlers(bus, session_factory=lambda: db)
    event = SessionResult(
        session_id=sid,
        student_id=changed.student_id,
        node_id=changed.node_id,
        class_id=changed.class_id,
        state=MasteryState.MASTERED,
        verdict=Verdict.PASSED,
        total_score=85,
        criteria=[],
    )
    bus.publish(TOPIC_SESSION_COMPLETED, event)

    data = json.loads(ev.feedback)
    assert data["unlockedNodes"] == [str(u1), str(u2)]
    db.commit.assert_called_once()
    db.close.assert_called_once()
