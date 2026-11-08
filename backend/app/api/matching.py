"""Ghép cặp bạn cùng tiến – MX4, FR-PM-01…08. Chủ: Long (C2-14, C2-15). Hợp đồng: `schemas/matching.py`."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, Lecturer, LecturerOrStudent, Student
from app.core.errors import AppError
from app.db.session import get_db
from app.models.schemas.matching import (
    MatchAdjust,
    MatchingStats,
    MatchOut,
    OptIn,
    ReviewWindowOut,
    ReviewWindowRequest,
    RoundOut,
    RoundRequest,
)
from app.models.users import Enrollment
from app.services.live_matching import LiveMatching
from app.services.matching import MatchingService

router = APIRouter(tags=["matching"])

__all__ = ["MatchOut", "OptIn", "ReviewWindowOut", "ReviewWindowRequest", "RoundOut", "RoundRequest", "router"]


def get_matching_service(db: Session = Depends(get_db)) -> MatchingService:
    return MatchingService(db)


Matching = Annotated[MatchingService, Depends(get_matching_service)]


@router.put("/classes/{class_id}/nodes/{node_id}/review-window", response_model=ReviewWindowOut)
def set_review_window(
    class_id: UUID,
    node_id: UUID,
    body: ReviewWindowRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Lecturer,
) -> ReviewWindowOut:
    """C2-15: GV đặt hạn kiểm tra bài cũ của nút. Trong hạn ghép cặp chạy theo sự kiện: người Đạt dạy tối đa 3 người
    chưa Đạt, không đạt ⇒ ghép ngay. Đặt lại cho cùng nút thì dời hạn."""
    return LiveMatching(db).set_window(class_id, node_id, body.deadline_at, user)


@router.get("/classes/{class_id}/review-windows", response_model=list[ReviewWindowOut])
def list_review_windows(
    class_id: UUID, db: Session = Depends(get_db), user: CurrentUser = Lecturer
) -> list[ReviewWindowOut]:
    """C2-15: các hạn của lớp kèm số người dạy, số bạn đã có cặp và bạn còn chờ (GV giảng trực tiếp / ghép tay)."""
    return LiveMatching(db).list_windows(class_id, user)


@router.post("/classes/{class_id}/matching-rounds", response_model=RoundOut, status_code=201)
def run_round(class_id: UUID, body: RoundRequest, svc: Matching, user: CurrentUser = Lecturer) -> RoundOut:
    """TC13: lớp có An–Châu bù trừ hai chiều ⇒ gợi ý An ↔ Châu (N5 / N4). GV phụ trách lớp mới được chạy."""
    return svc.run_round(class_id, "MANUAL", user, body.priority_node_id)


@router.get("/classes/{class_id}/matches", response_model=list[MatchOut])
def list_matches(class_id: UUID, svc: Matching, user: CurrentUser = LecturerOrStudent) -> list[MatchOut]:
    """SV-07: cặp của chính SV. GV-09: mọi cặp của lớp (GV phụ trách)."""
    return svc.list_matches(class_id, user)


@router.put("/enrollments/{enrollment_id}/peer-opt-in", response_model=OptIn)
def peer_opt_in(enrollment_id: UUID, body: OptIn, svc: Matching, user: CurrentUser = Student) -> OptIn:
    """FR-PM-01 / BR-10: tắt tham gia ⇒ các gợi ý đang chờ của SV bị từ chối."""
    return OptIn(peer_opt_in=svc.set_opt_in(enrollment_id, user, body.peer_opt_in))


@router.get("/classes/{class_id}/peer-opt-in", response_model=OptIn)
def get_class_peer_opt_in(class_id: UUID, db: Session = Depends(get_db), user: CurrentUser = Student) -> OptIn:
    """FR-PM-01: Lấy trạng thái tham gia ghép cặp của SV ở lớp này."""
    enr = db.scalar(select(Enrollment).where(Enrollment.class_id == class_id, Enrollment.student_id == user.id))
    if enr is None:
        raise AppError(403, "NOT_ENROLLED", "Bạn chưa tham gia lớp này")
    return OptIn(peer_opt_in=bool(enr.peer_opt_in))


@router.put("/classes/{class_id}/peer-opt-in", response_model=OptIn)
def set_class_peer_opt_in(class_id: UUID, body: OptIn, svc: Matching, user: CurrentUser = Student) -> OptIn:
    """FR-PM-01 / BR-10: Bật / tắt tham gia ghép cặp theo lớp."""
    enr = svc.db.scalar(select(Enrollment).where(Enrollment.class_id == class_id, Enrollment.student_id == user.id))
    if enr is None:
        raise AppError(403, "NOT_ENROLLED", "Bạn chưa tham gia lớp này")
    return OptIn(peer_opt_in=svc.set_opt_in(enr.id, user, body.peer_opt_in))


@router.post("/matches/{match_id}/{action}", response_model=MatchOut)
def respond(
    match_id: UUID,
    action: Literal["accept", "decline", "studied"],
    svc: Matching,
    user: CurrentUser = Student,
) -> MatchOut:
    """POST /matches/{m}/accept | decline | studied (BR-09, BR-10)."""
    return svc.respond(match_id, user, action)


@router.patch("/matches/{match_id}", response_model=MatchOut)
def adjust_match(match_id: UUID, body: MatchAdjust, svc: Matching, user: CurrentUser = Lecturer) -> MatchOut:
    """GV điều chỉnh cặp thủ công (FR-PM-08): `cancel` hủy cặp, hoặc `replaceStudentId` + `withStudentId` thay một SV
    (nút dạy / học tính lại, cặp quay về PROPOSED)."""
    return svc.adjust_match(match_id, user, body)


@router.get("/classes/{class_id}/matching-stats", response_model=MatchingStats)
def matching_stats(class_id: UUID, svc: Matching, user: CurrentUser = Lecturer) -> MatchingStats:
    """Hiệu quả ghép cặp (6.6.6): tỉ lệ chấp nhận, học cùng, mục được xác nhận Đạt."""
    return svc.stats(class_id, user)
