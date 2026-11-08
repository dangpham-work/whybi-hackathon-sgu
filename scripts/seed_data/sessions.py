"""Dựng lại tiến độ SV cho một lớp bằng cách ghi thẳng qua MasteryService (không gọi LLM/orchestrator),
mô phỏng kịch bản: dồn lỗi vào một nút (demo MX3 cảnh báo "Nên giảng lại X"), còn vài SV chưa đụng tới
(để demo phiên thật MX2), và bật tham gia ghép cặp cho một nhóm SV (demo MX4).
"""

from __future__ import annotations

import random
from uuid import UUID, uuid4

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.enums import MasteryState, Verdict
from app.models.schemas.session import SessionResult
from app.models.session import TeachingSession
from app.models.users import Enrollment
from app.services.mastery import MasteryService

LIVE_DEMO_RESERVED = 3  # SV cuối mỗi lớp không đụng tới – còn nguyên để demo phiên thật khi lên lớp
PEER_OPT_IN_COUNT = 10  # SV đầu mỗi lớp bật tham gia ghép cặp
FAIL_RATE_ROOT_CAUSE = 0.7
FAIL_RATE_NORMAL = 0.15
COVERAGE_RATIO = 0.65  # chỉ học tới ~65% số nút theo thứ tự tiên quyết – còn chỗ tăng trưởng khi demo


def _result(sid: UUID, student_id: UUID, node_id: UUID, class_id: UUID, passed: bool) -> SessionResult:
    return SessionResult(
        session_id=sid,
        student_id=student_id,
        node_id=node_id,
        class_id=class_id,
        state=MasteryState.MASTERED if passed else MasteryState.NOT_PASSED,
        verdict=Verdict.PASSED if passed else Verdict.FAILED,
        total_score=82.0 if passed else 45.0,
        criteria=[],
    )


def _hoc(db: Session, svc: MasteryService, student_id: UUID, node_id: UUID, class_id: UUID, passed: bool) -> None:
    sid = uuid4()
    db.add(
        TeachingSession(
            id=sid, student_id=student_id, node_id=node_id, class_id=class_id, input_mode="TEXT", status="CREATED"
        )
    )
    db.flush()
    svc.start_session(student_id, node_id, sid)
    svc.apply_result(_result(sid, student_id, node_id, class_id, passed))


def backfill(
    db: Session,
    class_id: UUID,
    student_ids: list[UUID],
    node_order: list[tuple[str, UUID]],
    root_cause_code: str,
    seed: int,
) -> None:
    """`node_order`: [(mã nút, id nút), ...] theo đúng thứ tự tiên quyết (cha trước con, như trees.py sinh ra)."""
    rng = random.Random(seed)
    svc = MasteryService(db)
    reserved = set(student_ids[-LIVE_DEMO_RESERVED:]) if len(student_ids) > LIVE_DEMO_RESERVED else set()
    learners = [s for s in student_ids if s not in reserved]
    cutoff = max(1, int(len(node_order) * COVERAGE_RATIO))
    for student_id in learners:
        for code, node_id in node_order[:cutoff]:
            fail_rate = FAIL_RATE_ROOT_CAUSE if code == root_cause_code else FAIL_RATE_NORMAL
            passed = rng.random() >= fail_rate
            _hoc(db, svc, student_id, node_id, class_id, passed)
            if not passed:
                break  # nút chưa Đạt ⇒ nút sau vẫn khóa (DAG) – dừng chuỗi của SV này ở đây
    if student_ids:
        db.execute(
            update(Enrollment)
            .where(Enrollment.class_id == class_id, Enrollment.student_id.in_(student_ids[:PEER_OPT_IN_COUNT]))
            .values(peer_opt_in=True)
        )
    db.commit()
