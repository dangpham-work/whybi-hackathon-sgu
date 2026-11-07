"""Ghép cặp bạn cùng tiến – MX4, FR-PM-01…08. Chủ: Long (C2-14, C2-15)."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter

from app.api.deps import CurrentUser, Lecturer, Student
from app.core.errors import NotImplementedYet
from app.models.enums import MatchStatus
from app.models.schemas.common import ApiModel

router = APIRouter(tags=["matching"])


class RoundRequest(ApiModel):
    priority_node_id: UUID | None = None  # "Ghép cặp ưu tiên N5" (FR-PM-04)


class MatchOut(ApiModel):
    id: UUID
    partner_name: str
    i_teach: list[str]
    i_learn: list[str]
    status: MatchStatus
    weight: float
    expires_at: str


class RoundOut(ApiModel):
    id: UUID
    participant_count: int
    total_weight: float
    matches: list[MatchOut]


class OptIn(ApiModel):
    peer_opt_in: bool


@router.post("/classes/{class_id}/matching-rounds", response_model=RoundOut, status_code=201)
def run_round(class_id: UUID, body: RoundRequest, user: CurrentUser = Lecturer) -> RoundOut:
    """TC13: lớp có An–Châu bù trừ hai chiều ⇒ gợi ý An ↔ Châu (N5 / N4)."""
    raise NotImplementedYet("C2-14")


@router.get("/classes/{class_id}/matches", response_model=list[MatchOut])
def list_matches(class_id: UUID, user: CurrentUser = Student) -> list[MatchOut]:
    """SV-07 / GV-09."""
    raise NotImplementedYet("C2-14")


@router.put("/enrollments/{enrollment_id}/peer-opt-in", response_model=OptIn)
def peer_opt_in(enrollment_id: UUID, body: OptIn, user: CurrentUser = Student) -> OptIn:
    raise NotImplementedYet("C2-14")


@router.post("/matches/{match_id}/{action}", response_model=MatchOut)
def respond(
    match_id: UUID,
    action: Literal["accept", "decline", "studied"],
    user: CurrentUser = Student,
) -> MatchOut:
    """POST /matches/{m}/accept | decline | studied (BR-09, BR-10)."""
    raise NotImplementedYet("C2-14")


@router.patch("/matches/{match_id}", response_model=MatchOut)
def adjust_match(match_id: UUID, user: CurrentUser = Lecturer) -> MatchOut:
    """GV điều chỉnh cặp thủ công (FR-PM-08, vòng 2)."""
    raise NotImplementedYet("C2-15")
