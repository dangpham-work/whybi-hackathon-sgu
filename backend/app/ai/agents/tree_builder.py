"""Dựng cây kỹ năng nháp từ văn bản giáo trình (mục 6.1.2–6.1.3). Chủ: Đăng (C1-10).

Trang đã bóc (C1-09) → chia chương → LLM trích khái niệm theo JSON Schema (gateway tự thử lại khi sai cấu trúc) →
gộp trùng (cosine ≥ 0,9, LLM xác nhận) → sinh cặp tiên quyết ứng viên (tránh O(n²)) → LLM phán đoán, giữ
confidence ≥ 0,6 → `TreeVersion` nháp. Phá chu trình / rút gọn bắc cầu do
`SkillTreeService.create_version(sanitize_graph=True)`.
Nội dung giáo trình luôn là DỮ LIỆU (bọc `<syllabus_text>`).
"""

import math
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.ai.gateway import LLMGateway
from app.ai.prompts import render_prompt, wrap_student_text
from app.core.errors import AppError
from app.models.enums import BloomLevel, EdgeSource
from app.models.schemas.tree import Edge, Node, TreeVersion

MIN_CONFIDENCE = 0.6  # mục 6.1.3
MERGE_COSINE = 0.9  # mục 6.1.2
MAX_CHAPTER_CHARS = 12_000  # chương dài hơn thì tách phần để vừa ngữ cảnh LLM
FALLBACK_PAGES = 5  # giáo trình không có tiêu đề "Chương" ⇒ gom mỗi 5 trang
MAX_CONCEPTS = 12  # mỗi chương / phần
TOP_SIMILAR = 3  # ứng viên theo embedding gần nhất cho mỗi nút
MAX_CANDIDATES = 6
LLM_WORKERS = 8  # MT1: 30 trang ≤ 3 phút ⇒ gọi LLM song song

_CHAPTER = re.compile(r"^\s*(chương|bài|phần)\s+(\d+|[ivxlc]+)\b", re.I)


class Concept(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]+$", max_length=60)
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(max_length=400)
    chapter_ref: str
    bloom_level: BloomLevel


class ConceptList(BaseModel):
    concepts: list[Concept]
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "concepts": [
                        {
                            "key": "khai_niem_mau",
                            "title": "Khái niệm mẫu",
                            "description": "Khái niệm mẫu của chế độ giả lập.",
                            "chapter_ref": "Chương 1",
                            "bloom_level": "UNDERSTAND",
                        }
                    ]
                }
            ]
        }
    )


class PrereqItem(BaseModel):
    from_key: str
    is_prerequisite: bool
    confidence: float = Field(ge=0, le=1)
    reason: str = ""


class PrereqJudgement(BaseModel):
    items: list[PrereqItem]


class MergeDecision(BaseModel):
    merge: bool


@dataclass
class Chapter:
    ref: str
    text: str


def _fixed_groups(pages: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    return [("", pages[i : i + FALLBACK_PAGES]) for i in range(0, len(pages), FALLBACK_PAGES)]


def split_chapters(pages: list[dict[str, Any]]) -> list[Chapter]:
    """`pages`: JSON của C1-09 `[{number, text, headings}]`. Tiêu đề "Chương/Bài/Phần n" mở chương mới; không có
    tiêu đề nào thì gom FALLBACK_PAGES trang. Mỗi trang đánh dấu `[Trang n]` để giữ vị trí cho trích dẫn."""
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    for p in pages:
        title = next((h for h in p.get("headings", []) if _CHAPTER.match(h)), None)
        if title or not groups:
            groups.append((title or "", []))
        groups[-1][1].append(p)
    if len(groups) == 1 and not groups[0][0]:
        groups = _fixed_groups(pages)
    out: list[Chapter] = []
    for ref, ps in groups:
        ref = ref or f"Trang {ps[0]['number']}–{ps[-1]['number']}"
        buf: list[str] = []
        size = 0
        for p in ps:
            text = f"[Trang {p['number']}]\n{p['text'].strip()}"[:MAX_CHAPTER_CHARS]
            if buf and size + len(text) > MAX_CHAPTER_CHARS:
                out.append(Chapter(ref, "\n\n".join(buf)))
                buf, size = [], 0
            buf.append(text)
            size += len(text)
        if buf:
            out.append(Chapter(ref, "\n\n".join(buf)))
    return [c for c in out if re.sub(r"\[Trang \d+\]|\s", "", c.text)]


def cosine(a: list[float], b: list[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=False)) / (na * nb) if na and nb else 0.0


class TreeBuilder:
    def __init__(self, gateway: LLMGateway, *, max_concepts: int = MAX_CONCEPTS, workers: int = LLM_WORKERS):
        self.gw = gateway
        self.max_concepts = max_concepts
        self.workers = workers

    # --- 6.1.2 ---

    def _extract(self, ch: Chapter) -> list[Concept]:
        system = render_prompt("tree_concepts", chapter_ref=ch.ref, max_concepts=str(self.max_concepts))
        msgs = [
            {"role": "system", "content": system},
            {"role": "user", "content": wrap_student_text(ch.text, "syllabus_text")},
        ]
        return self.gw.call_json(ConceptList, msgs).concepts[: self.max_concepts]

    def extract_concepts(self, chapters: list[Chapter]) -> list[Concept]:
        with ThreadPoolExecutor(self.workers) as ex:
            per_chapter = list(ex.map(self._extract, chapters))
        return [c for cs in per_chapter for c in cs]

    def dedupe(self, concepts: list[Concept]) -> list[Concept]:
        """Gộp trùng: cosine(tiêu đề + mô tả) ≥ 0,9 với khái niệm đã giữ ⇒ LLM xác nhận; giữ tên theo giáo trình
        (bản xuất hiện trước). Khóa trùng nhưng khác khái niệm ⇒ đổi khóa `_2`, `_3`…"""
        vecs = self.gw.embed([f"{c.title}. {c.description}" for c in concepts])
        kept: list[Concept] = []
        kept_vecs: list[list[float]] = []
        for c, v in zip(concepts, vecs, strict=True):
            twin = next((i for i, kv in enumerate(kept_vecs) if cosine(v, kv) >= MERGE_COSINE), None)
            if twin is not None and self._same(kept[twin], c):
                continue
            used = {k.key for k in kept}
            key, n = c.key, 2
            while key in used:
                key, n = f"{c.key[:55]}_{n}", n + 1
            kept.append(c.model_copy(update={"key": key}))
            kept_vecs.append(v)
        return kept

    def _same(self, a: Concept, b: Concept) -> bool:
        system = render_prompt(
            "tree_merge",
            title_a=a.title,
            description_a=a.description,
            title_b=b.title,
            description_b=b.description,
        )
        return self.gw.call_json(MergeDecision, [{"role": "system", "content": system}]).merge

    # --- 6.1.3 ---

    def candidate_pairs(self, concepts: list[Concept]) -> dict[str, list[Concept]]:
        """Với mỗi B: A đứng trước B trong giáo trình và (mô tả B nhắc tên A, hoặc A nằm trong TOP_SIMILAR nút
        gần B nhất theo embedding). Số cặp ~ O(n) thay vì O(n²)."""
        vecs = self.gw.embed([f"{c.title}. {c.description}" for c in concepts])
        out: dict[str, list[Concept]] = {}
        for j, b in enumerate(concepts):
            before = range(j)
            named = {i for i in before if concepts[i].title.lower() in b.description.lower()}
            near = sorted(before, key=lambda i: cosine(vecs[i], vecs[j]), reverse=True)[:TOP_SIMILAR]
            picked = sorted(named | set(near))[-MAX_CANDIDATES:]
            if picked:
                out[b.key] = [concepts[i] for i in picked]
        return out

    def _judge(self, b: Concept, cands: list[Concept]) -> list[Edge]:
        listing = "\n".join(f'- from_key "{a.key}": {a.title} – {a.description}' for a in cands)
        system = render_prompt(
            "tree_prereq", target_title=b.title, target_description=b.description, candidates=listing
        )
        res = self.gw.call_json(PrereqJudgement, [{"role": "system", "content": system}])
        valid = {a.key for a in cands}
        best: dict[str, float] = {}
        for it in res.items:
            if it.is_prerequisite and it.confidence >= MIN_CONFIDENCE and it.from_key in valid:
                best[it.from_key] = max(best.get(it.from_key, 0), it.confidence)
        return [Edge(from_key=k, to_key=b.key, source=EdgeSource.AI, confidence=c) for k, c in best.items()]

    def infer_edges(self, concepts: list[Concept]) -> list[Edge]:
        pairs = self.candidate_pairs(concepts)
        by_key = {c.key: c for c in concepts}
        with ThreadPoolExecutor(self.workers) as ex:
            results = list(ex.map(lambda kv: self._judge(by_key[kv[0]], kv[1]), pairs.items()))
        return [e for es in results for e in es]

    # --- toàn bộ ---

    def build(self, pages: list[dict[str, Any]], on_step: Callable[[int, str], None] | None = None) -> TreeVersion:
        step = on_step or (lambda _p, _s: None)
        chapters = split_chapters(pages)
        if not chapters:
            raise AppError(422, "NO_CONTENT", "Tài liệu không có nội dung để dựng cây")
        step(15, "CONCEPTS")
        concepts = self.extract_concepts(chapters)
        if not concepts:
            raise AppError(422, "NO_CONCEPTS", "Không trích được khái niệm nào từ tài liệu")
        step(50, "DEDUPE")
        concepts = self.dedupe(concepts)
        step(65, "PREREQUISITES")
        edges = self.infer_edges(concepts)
        step(90, "TREE")
        nodes = [
            Node(
                key=c.key,
                code=f"N{i}",
                title=c.title,
                description=c.description,
                chapter_ref=c.chapter_ref,
                bloom_level=c.bloom_level,
            )
            for i, c in enumerate(concepts, 1)
        ]
        return TreeVersion(nodes=nodes, edges=edges, change_note="Cây nháp do AI trích từ giáo trình")
