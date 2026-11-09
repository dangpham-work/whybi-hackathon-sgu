"""Dựng cây kỹ năng nháp từ văn bản giáo trình (mục 6.1.2–6.1.3). Chủ: Đăng (C1-10).

Trang đã bóc (C1-09) → chia chương → LLM trích khái niệm theo JSON Schema (gateway tự thử lại khi sai cấu trúc) →
gộp trùng (cosine ≥ 0,9, LLM xác nhận) → sinh cặp tiên quyết ứng viên (tránh O(n²)) → LLM phán đoán, giữ
confidence ≥ 0,6 → `TreeVersion` nháp. Phá chu trình / rút gọn bắc cầu do
`SkillTreeService.create_version(sanitize_graph=True)`.
Nội dung giáo trình luôn là DỮ LIỆU (bọc `<syllabus_text>`).
"""

import logging
import math
import re
import unicodedata
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

log = logging.getLogger(__name__)

MIN_CONFIDENCE = 0.6  # mục 6.1.3
MERGE_COSINE = 0.9  # mục 6.1.2
MAX_CHAPTER_CHARS = 12_000  # chương dài hơn thì tách phần để vừa ngữ cảnh LLM
FALLBACK_PAGES = 5  # giáo trình không có tiêu đề "Chương" ⇒ gom mỗi 5 trang
MAX_CONCEPTS = 12  # mỗi chương / phần
TOP_SIMILAR = 3  # ứng viên theo embedding gần nhất cho mỗi nút
MAX_CANDIDATES = 6
MIN_CANDIDATE_COSINE = 0.35  # ứng viên chỉ-theo-embedding phải đủ gần; không đủ thì bỏ, đỡ cạnh rác và đỡ lượt gọi LLM
LLM_WORKERS = 8  # MT1: 30 trang ≤ 3 phút ⇒ gọi LLM song song

_CHAPTER = re.compile(r"^\s*(chương|bài|phần)\s+(\d+|[ivxlc]+)\b", re.I)


class Concept(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]+$", max_length=60)
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(max_length=400)
    chapter_ref: str
    bloom_level: BloomLevel


class Located(Concept):
    """Khái niệm kèm vị trí trong giáo trình (hệ thống gắn, không phải LLM trả): khoảng trang của đoạn nguồn."""

    page_from: int | None = None
    page_to: int | None = None


_REJECT_FILE_EXT = re.compile(
    r"\.(py|ipynb|txt|md|docx?|pdf|sh|ya?ml|json|env|csv|zip|tar|gz|toml|ini|cfg|rst|log|lock)$",
    re.I,
)
_REJECT_FILENAMES = {
    "dockerfile",
    "requirements.txt",
    "makefile",
    ".gitignore",
    "gitignore",
    "setup.py",
    "package.json",
    "docker-compose.yml",
    "docker-compose.yaml",
}
_REJECT_BOILERPLATE_TITLES = {
    "project root",
    "project structure",
    "source code folder",
    "environment files",
    "requirements file",
    "metadata file",
    "using jupyter notebooks vs. python scripts",
    "using jupyter notebooks vs python scripts",
}
_REJECT_FOLDER_PREFIXES = {
    "project",
    "data",
    "notebooks",
    "notebook",
    "scripts",
    "script",
    "source",
    "src",
    "results",
    "result",
    "config",
    "configuration",
    "tests",
    "test",
    "logs",
    "log",
    "saved objects",
    "saved object",
    "models",
    "documentation",
    "doc",
    "docs",
    "dataset",
    "datasets",
    "asset",
    "assets",
}


def is_boilerplate_concept(c: Concept) -> bool:
    """Loại bỏ các nút rác do LLM trích xuất nhầm từ cấu trúc thư mục repo / tệp tin dự án."""
    title = c.title.strip().casefold()
    key = c.key.strip().casefold()

    if _REJECT_FILE_EXT.search(title):
        return True
    if any(title.endswith(ext) for ext in (".py", ".txt", ".md", ".sh", ".json", ".yaml", ".yml", ".env")):
        return True
    if title in _REJECT_FILENAMES:
        return True
    if title in _REJECT_BOILERPLATE_TITLES:
        return True
    if title.endswith((" folder", " directory", " dir")):
        prefix = title.rsplit(" ", 1)[0].strip()
        if prefix in _REJECT_FOLDER_PREFIXES:
            return True
    if key in {
        "template_py",
        "requirements_txt",
        "dockerfile",
        "project_root",
        "project_structure",
        "data_folder",
        "notebooks_folder",
        "scripts_folder",
        "results_folder",
        "config_folder",
        "environment_files",
        "tests_folder",
        "logs_folder",
        "saved_objects_folder",
        "requirements_file",
        "metadata_file",
    }:
        return True
    return False


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
    page_from: int | None = None
    page_to: int | None = None


def _norm(s: str) -> str:
    """Hạ chữ thường (NFC), bỏ dấu câu, gộp khoảng trắng – so tên khái niệm theo từ nguyên vẹn."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", unicodedata.normalize("NFC", s).casefold())).strip()


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


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
        first = last = None
        for p in ps:
            text = f"[Trang {p['number']}]\n{p['text'].strip()}"[:MAX_CHAPTER_CHARS]
            if buf and size + len(text) > MAX_CHAPTER_CHARS:
                out.append(Chapter(ref, "\n\n".join(buf), first, last))
                buf, size, first = [], 0, None
            buf.append(text)
            size += len(text)
            first = p["number"] if first is None else first
            last = p["number"]
        if buf:
            out.append(Chapter(ref, "\n\n".join(buf), first, last))
    return [c for c in out if re.sub(r"\[Trang \d+\]|\s", "", c.text)]


def _toc_chapter(toc: list[tuple[str, int, int]] | None, page: int | None) -> str | None:
    """Tiêu đề chương trong mục lục chứa `page` (cắt 100 ký tự cho vừa cột)."""
    if not toc or page is None:
        return None
    return next((t[:100] for t, start, end in toc if start <= page <= end), None)


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
        found = self.gw.call_json(ConceptList, msgs).concepts[: self.max_concepts]
        valid = [c for c in found if not is_boilerplate_concept(c)]
        if len(valid) < len(found):
            log.info("Đã lọc bỏ %d khái niệm dạng tệp/thư mục dự án từ %s", len(found) - len(valid), ch.ref)
        # chương do hệ thống tách (không tin chữ LLM tự viết) + khoảng trang của đoạn nguồn
        return [
            Located(**{**c.model_dump(), "chapter_ref": ch.ref[:100]}, page_from=ch.page_from, page_to=ch.page_to)
            for c in valid
        ]

    def extract_concepts(
        self, chapters: list[Chapter], step: Callable[[int, str], None] | None = None
    ) -> list[Concept]:
        step = step or (lambda _p, _s: None)
        out: list[Concept] = []
        batches = list(range(0, len(chapters), self.workers))
        total = max(1, len(batches))
        with ThreadPoolExecutor(self.workers) as ex:
            for n, i in enumerate(batches, 1):
                batch = chapters[i : i + self.workers]
                out.extend(c for cs in ex.map(self._extract, batch) for c in cs)
                # % thật theo số lô đã xong (15→49, mốc 50 là DEDUPE) + kiểm tra hủy, không chờ hết cả giáo trình
                step(15 + round(34 * n / total), "CONCEPTS")
        return out

    def dedupe(self, concepts: list[Concept]) -> list[Concept]:
        """Gộp trùng, giữ tên theo giáo trình (bản xuất hiện trước):
        1. cùng tên sau chuẩn hóa (hoa/thường, dấu câu, khoảng trắng) ⇒ gộp luôn, không tốn lượt LLM;
        2. không thì lấy bản đã giữ GIỐNG NHẤT, cosine(tiêu đề + mô tả) ≥ 0,9 ⇒ LLM xác nhận.
        Gộp thì giữ mô tả đầy đủ hơn. Khóa trùng nhưng khác khái niệm ⇒ đổi khóa `_2`, `_3`…
        Vectơ giữ lại trong `_vecs` để bước chọn ứng viên tiên quyết dùng lại (chỉ embed một lần)."""
        texts = [f"{c.title}. {c.description}" for c in concepts]
        vecs = [_unit(v) for v in self.gw.embed(texts)]
        kept: list[Concept] = []
        kept_vecs: list[list[float]] = []
        kept_texts: list[str] = []
        by_name: dict[str, int] = {}
        for c, v, text in zip(concepts, vecs, texts, strict=True):
            twin = by_name.get(_norm(c.title))
            if twin is None and kept_vecs:
                best = max(range(len(kept_vecs)), key=lambda i: _dot(v, kept_vecs[i]))
                if _dot(v, kept_vecs[best]) >= MERGE_COSINE and self._same(kept[best], c):
                    twin = best
            if twin is not None:
                if len(c.description) > len(kept[twin].description):
                    kept[twin] = kept[twin].model_copy(update={"description": c.description})
                    kept_texts[twin] = f"{kept[twin].title}. {c.description}"
                continue
            used = {k.key for k in kept}
            key, n = c.key, 2
            while key in used:
                key, n = f"{c.key[:55]}_{n}", n + 1
            by_name.setdefault(_norm(c.title), len(kept))
            kept.append(c.model_copy(update={"key": key}))
            kept_vecs.append(v)
            kept_texts.append(text)
        self._vecs = {k.key: (t, v) for k, t, v in zip(kept, kept_texts, kept_vecs, strict=True)}
        return kept

    def _vectors(self, concepts: list[Concept]) -> list[list[float]]:
        """Vectơ đã chuẩn hóa độ dài; dùng lại kết quả của `dedupe` nếu cùng khóa và cùng nội dung."""
        texts = [f"{c.title}. {c.description}" for c in concepts]
        cache = getattr(self, "_vecs", {})
        if all(c.key in cache and cache[c.key][0] == t for c, t in zip(concepts, texts, strict=True)):
            return [cache[c.key][1] for c in concepts]
        return [_unit(v) for v in self.gw.embed(texts)]

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
        """Với mỗi B: A đứng trước B trong giáo trình và (mô tả B nhắc tên A nguyên từ, hoặc A nằm trong TOP_SIMILAR
        nút gần B nhất theo embedding VÀ cosine ≥ MIN_CANDIDATE_COSINE). Quá MAX_CANDIDATES thì giữ ứng viên được
        nhắc tên rồi giống nhất, không cắt theo thứ tự xuất hiện. Không có ứng viên ⇒ không tốn lượt LLM."""
        vecs = self._vectors(concepts)
        names = [_norm(c.title) for c in concepts]
        descs = [f" {_norm(c.description)} " for c in concepts]
        out: dict[str, list[Concept]] = {}
        for j, b in enumerate(concepts):
            sim = {i: _dot(vecs[i], vecs[j]) for i in range(j)}
            named = sorted((i for i in sim if names[i] and f" {names[i]} " in descs[j]), key=lambda i: -sim[i])
            near = [i for i in sorted(sim, key=lambda i: -sim[i])[:TOP_SIMILAR] if sim[i] >= MIN_CANDIDATE_COSINE]
            picked = sorted((named + [i for i in near if i not in named])[:MAX_CANDIDATES])
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

    def infer_edges(self, concepts: list[Concept], step: Callable[[int, str], None] | None = None) -> list[Edge]:
        step = step or (lambda _p, _s: None)
        items = list(self.candidate_pairs(concepts).items())
        by_key = {c.key: c for c in concepts}
        out: list[Edge] = []
        batches = list(range(0, len(items), self.workers))
        total = max(1, len(batches))
        with ThreadPoolExecutor(self.workers) as ex:
            for n, i in enumerate(batches, 1):
                batch = items[i : i + self.workers]
                out.extend(e for es in ex.map(lambda kv: self._judge(by_key[kv[0]], kv[1]), batch) for e in es)
                # % thật theo số lô đã xong (65→89, mốc 90 là TREE) + kiểm tra hủy
                step(65 + round(24 * n / total), "PREREQUISITES")
        return out

    # --- toàn bộ ---

    def build(
        self,
        pages: list[dict[str, Any]],
        on_step: Callable[[int, str], None] | None = None,
        toc_chapters: list[tuple[str, int, int]] | None = None,
    ) -> TreeVersion:
        """`toc_chapters`: [(tiêu đề, trang đầu, trang cuối)] từ mục lục (TocStep) – có thì chương của nút lấy từ đây
        (ổn định, đúng tên giáo trình), không thì dùng tiêu đề do `split_chapters` tách."""
        step = on_step or (lambda _p, _s: None)
        chapters = split_chapters(pages)
        if not chapters:
            raise AppError(422, "NO_CONTENT", "Tài liệu không có nội dung để dựng cây")
        step(15, "CONCEPTS")
        concepts = self.extract_concepts(chapters, step)
        if not concepts:
            raise AppError(422, "NO_CONCEPTS", "Không trích được khái niệm nào từ tài liệu")
        step(50, "DEDUPE")
        concepts = self.dedupe(concepts)
        step(65, "PREREQUISITES")
        edges = self.infer_edges(concepts, step)
        step(90, "TREE")
        nodes = [
            Node(
                key=c.key,
                code=f"N{i}",
                title=c.title,
                description=c.description,
                chapter_ref=_toc_chapter(toc_chapters, getattr(c, "page_from", None)) or c.chapter_ref,
                source_page_start=getattr(c, "page_from", None),
                source_page_end=getattr(c, "page_to", None),
                bloom_level=c.bloom_level,
            )
            for i, c in enumerate(concepts, 1)
        ]
        return TreeVersion(nodes=nodes, edges=edges, change_note="Cây nháp do AI trích từ giáo trình")
