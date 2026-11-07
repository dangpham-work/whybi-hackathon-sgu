"""Sinh rubric một nút bằng RAG trên giáo trình của GV (mục 6.1.5, Bảng 6.1). Chủ: Đăng (C1-11).

Truy hồi đoạn giáo trình liên quan đến nút → LLM soạn ý chính / quan niệm sai / tình huống phản biện / mức Bloom →
đánh số KP/MC/SC → trang trích dẫn luôn nằm trong các đoạn đã truy hồi (LLM bịa trang thì bị loại). Rubric sinh ra
luôn `approved=False`: GV phải duyệt trước khi phát hành (BR-05).
"""

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.ai.gateway import LLMGateway
from app.ai.prompts import render_prompt, wrap_student_text
from app.core.errors import AppError
from app.models.enums import BloomLevel
from app.models.schemas.tree import (
    ChallengeScenarioSchema,
    KeyPointSchema,
    MisconceptionSchema,
    Node,
    Rubric,
)
from app.services.retrieval import Passage

TOP_PASSAGES = 5
MAX_SOURCE_PAGES = 10
MIN_SCENARIOS = 3  # mục 6.1.5 / Bảng 6.1: tối thiểu 3 câu phản biện


class _KeyPoint(BaseModel):
    content: str = Field(min_length=1, max_length=600)
    is_required: bool = True


class _Misconception(BaseModel):
    content: str = Field(min_length=1, max_length=600)
    probe_question: str | None = None
    is_critical: bool = False


class _Scenario(BaseModel):
    scenario: str = Field(min_length=1, max_length=600)
    bloom_level: BloomLevel = BloomLevel.APPLY
    expected_points: str | None = None


class RubricDraft(BaseModel):
    """Đầu ra LLM (chưa có id, chưa kiểm trang)."""

    key_points: list[_KeyPoint] = Field(min_length=1)
    optional_points: list[str] = []
    misconceptions: list[_Misconception] = []
    scenarios: list[_Scenario] = Field(min_length=1)
    target_bloom: BloomLevel = BloomLevel.UNDERSTAND
    source_pages: list[int] = []
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "key_points": [{"content": "Ý chính mẫu của chế độ giả lập.", "is_required": True}],
                    "optional_points": [],
                    "misconceptions": [],
                    "scenarios": [{"scenario": "Tình huống mẫu?", "bloom_level": "APPLY", "expected_points": None}],
                    "target_bloom": "UNDERSTAND",
                    "source_pages": [],
                }
            ]
        }
    )


def passage_pages(passages: list[Passage]) -> list[int]:
    pages: set[int] = set()
    for p in passages:
        if p.page_from is not None:
            pages.update(range(p.page_from, (p.page_to or p.page_from) + 1))
    return sorted(pages)


def _format(passages: list[Passage]) -> str:
    out = []
    for p in passages:
        a, b = p.page_from, p.page_to
        label = f"[Trang {a}–{b}]" if a != b else f"[Trang {a}]"
        out.append(f"{label} {p.chapter or ''} {p.section_title or ''}\n{p.content}".strip())
    return "\n\n".join(out)


def query_for(node: Node) -> str:
    return f"{node.title}. {node.description or ''}".strip()


class RubricGenerator:
    def __init__(self, gateway: LLMGateway, *, pass_threshold: int = 70, scenario_count: int = MIN_SCENARIOS):
        self.gw = gateway
        self.pass_threshold = pass_threshold
        self.scenario_count = max(MIN_SCENARIOS, scenario_count)

    def generate(self, node: Node, passages: list[Passage]) -> Rubric:
        if not passages:
            raise AppError(
                422,
                "NO_SOURCE_MATERIAL",
                "Lớp chưa có giáo trình đã xử lý để sinh rubric – hãy tải giáo trình lên trước",
            )
        system = render_prompt(
            "rubric",
            node_title=node.title,
            node_description=node.description or "",
            scenario_count=str(self.scenario_count),
        )
        msgs = [
            {"role": "system", "content": system},
            {"role": "user", "content": wrap_student_text(_format(passages), "syllabus_text")},
        ]
        d = self.gw.call_json(RubricDraft, msgs)
        return self._to_rubric(d, passages)

    def _to_rubric(self, d: RubricDraft, passages: list[Passage]) -> Rubric:
        allowed = set(passage_pages(passages))
        pages = sorted({p for p in d.source_pages if p in allowed})
        if not pages:  # LLM không ghi hoặc bịa trang ⇒ dùng trang của đoạn khớp nhất
            top = passages[0]
            pages = list(range(top.page_from or 1, (top.page_to or top.page_from or 1) + 1))
        return Rubric(
            key_points=[
                KeyPointSchema(id=f"KP{i}", content=k.content, is_required=k.is_required)
                for i, k in enumerate(d.key_points, 1)
            ],
            optional_points=d.optional_points,
            misconceptions=[
                MisconceptionSchema(
                    id=f"MC{i}", content=m.content, probe_question=m.probe_question, is_critical=m.is_critical
                )
                for i, m in enumerate(d.misconceptions, 1)
            ],
            scenarios=[
                ChallengeScenarioSchema(
                    id=f"SC{i}", scenario=s.scenario, bloom_level=s.bloom_level, expected_points=s.expected_points
                )
                for i, s in enumerate(d.scenarios, 1)
            ],
            target_bloom=d.target_bloom,
            pass_threshold=self.pass_threshold,
            min_challenges=self.scenario_count,
            min_passed_challenges=max(1, math.ceil(self.scenario_count * 2 / 3)),
            source_pages=pages[:MAX_SOURCE_PAGES],
            approved=False,
        )


def class_params(cls: Any) -> dict[str, int]:
    """Ngưỡng Đạt và số câu phản biện do GV cấu hình cho lớp (FR-HM-08, C2-17)."""
    return {"pass_threshold": cls.pass_threshold, "scenario_count": cls.challenge_count}
