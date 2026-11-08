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
    scenario_type: str = "bottleneck_root_cause",
    peer_opt_in_count: int = 12,
) -> None:
    """`node_order`: [(mã nút, id nút), ...] theo đúng thứ tự tiên quyết.

    Dựng tiến độ khác nhau cho 5 lớp theo `scenario_type`:
    - bottleneck_root_cause (CTDL): nghẽn nặng ở nút gốc N5 (75% trượt), chặn nút sau.
    - high_performer (HDH): lớp giỏi, xanh mướt (85% qua), tiến độ sâu, chỉ chậm ở O6 (Deadlock).
    - early_stage (NMLT): lớp tân sinh viên, mới học 40% đầu cây, nửa sau cây LOCKED xám hoàn toàn.
    - bimodal_gap (MMT): phân hóa 2 cực, 15 bạn đầu giỏi xanh, các bạn sau đuối đỏ ở M9 (Subnet).
    - conceptual_hurdle (CSDL): thực hành SQL tốt, kẹt lý thuyết chuẩn hóa 3NF (D10).
    """
    rng = random.Random(seed)
    svc = MasteryService(db)
    reserved = set(student_ids[-LIVE_DEMO_RESERVED:]) if len(student_ids) > LIVE_DEMO_RESERVED else set()
    learners = [s for s in student_ids if s not in reserved]

    for idx, student_id in enumerate(learners):
        if scenario_type == "high_performer":
            cutoff = max(1, int(len(node_order) * 0.85))
            fn, fr = 0.05, 0.35
        elif scenario_type == "early_stage":
            cutoff = max(1, int(len(node_order) * 0.40))
            fn, fr = 0.15, 0.50
        elif scenario_type == "bimodal_gap":
            # 15 bạn đầu giỏi, các bạn sau đuối
            if idx < 15:
                cutoff = max(1, int(len(node_order) * 0.80))
                fn, fr = 0.08, 0.15
            else:
                cutoff = max(1, int(len(node_order) * 0.45))
                fn, fr = 0.30, 0.65
        elif scenario_type == "conceptual_hurdle":
            cutoff = max(1, int(len(node_order) * 0.60))
            fn, fr = 0.10, 0.65
        else:  # bottleneck_root_cause
            cutoff = max(1, int(len(node_order) * 0.65))
            fn, fr = 0.12, 0.75

        for code, node_id in node_order[:cutoff]:
            fail_rate = fr if code == root_cause_code else fn
            passed = rng.random() >= fail_rate
            _hoc(db, svc, student_id, node_id, class_id, passed)
            if not passed:
                break  # nút chưa Đạt ⇒ dừng chuỗi tiên quyết

    if student_ids and peer_opt_in_count > 0:
        db.execute(
            update(Enrollment)
            .where(Enrollment.class_id == class_id, Enrollment.student_id.in_(student_ids[:peer_opt_in_count]))
            .values(peer_opt_in=True)
        )
    db.commit()
