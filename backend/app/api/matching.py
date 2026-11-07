"""Ghép cặp bạn cùng tiến – MX4, FR-PM-01…08. Chủ: Long (C2-14, C2-15). Hợp đồng: `schemas/matching.py`."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, Lecturer, LecturerOrStudent, Student
from app.core.errors import NotImplementedYet
from app.db.session import get_db
from app.models.schemas.matching import MatchOut, OptIn, RoundOut, RoundRequest
from app.services.matching import MatchingService

router = APIRouter(tags=["matching"])

__all__ = ["MatchOut", "OptIn", "RoundOut", "RoundRequest", "router"]


def get_matching_service(db: Session = Depends(get_db)) -> MatchingService:
    return MatchingService(db)


Matching = Annotated[MatchingService, Depends(get_matching_service)]


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
def adjust_match(match_id: UUID, user: CurrentUser = Lecturer) -> MatchOut:
    """GV điều chỉnh cặp thủ công (FR-PM-08, vòng 2)."""
    raise NotImplementedYet("C2-15")
