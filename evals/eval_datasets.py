"""Schema + bộ đọc các bộ đánh giá trong evals/ (KT-04, Bảng 7.3 đề cương).

    cd backend && uv run python ../evals/run.py check   # đọc + kiểm mọi bộ, thoát 1 nếu có bộ hỏng

Mỗi bộ đọc theo schema Pydantic (extra="forbid"); dòng hỏng báo đúng `<file>:<dòng>`.
Mã tiêu chí / nhãn / cờ lấy từ hợp đồng `app/models/enums.py`; cây chuẩn đọc bằng `TreeVersion` (C2-02).
Dữ liệu thiếu so với chỉ tiêu (vd. < 50 kịch bản, chưa có file ghi âm) chỉ là cảnh báo, không phải lỗi schema.
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator

EVALS = Path(__file__).resolve().parent
REPO = EVALS.parent
sys.path.insert(0, str(REPO / "backend"))  # để `import app...` khi chạy từ bất kỳ đâu

from app.algorithms.dag import build_graph, find_cycle  # noqa: E402 – cùng luật chặn chu trình BR-01
from app.models.enums import CriterionCode, FlagType, Verdict  # noqa: E402
from app.models.schemas.tree import (  # noqa: E402
    ChallengeScenarioSchema,
    Edge,
    KeyPointSchema,
    MisconceptionSchema,
    Node,
    Rubric,
    TreeVersion,
)

SEED_TREE = REPO / "seed" / "tree_ctdl_gt.json"

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Score = Annotated[int, Field(ge=0, le=100)]  # thang 0–100 như CriterionScore (hợp đồng phiên C1-01)

# Chỉ tiêu cỡ dữ liệu (Bảng 7.3) – thiếu thì cảnh báo
TARGETS: dict[str, tuple[int, int | None]] = {
    "guard": (50, None),
    "judge": (60, 100),
    "tutee": (30, None),
    "stt": (30, None),
    "tree": (3, 5),
}


class DatasetError(ValueError):
    """Bộ dữ liệu không đọc được theo schema – thông điệp có `<file>:<dòng>` hoặc tên file."""


class _Row(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- guard/attacks.jsonl (KT-07) ----------

AttackType = Literal[
    "JAILBREAK",  # bỏ qua hướng dẫn / đòi Đạt
    "SYSTEM_SPOOF",  # giả danh hệ thống, giả GV
    "ROLEPLAY",  # nhập vai để vượt luật
    "ENCODING",  # giấu chỉ thị: base64, chữ tách, tiếng Anh, thẻ XML
    "ASK_TO_TEACH",  # đòi Tutee giảng hộ / lộ đáp án
    "PASTE",  # dán lời giải có sẵn
    "OFF_TOPIC",  # lạc đề
    "EMPTY_ANSWERS",  # trả lời rỗng / chiếu lệ
    "VOICE_INJECTION",  # chèn chỉ thị trong ghi âm
    "INAPPROPRIATE",  # nội dung không phù hợp
]


class AttackExpect(_Row):
    """Kỳ vọng kiểm được – ít nhất một trường. `flag` dùng FlagType của hợp đồng phiên."""

    flag: FlagType | None = None
    affects_score: bool | None = None
    judge_ignores: bool | None = None
    tutee_refuses: bool | None = None
    asks_back: bool | None = None
    redirects: bool | None = None
    next_question: Literal["NEW_SCENARIO"] | None = None
    criterion_low: CriterionCode | None = None
    state: Verdict | None = None
    via: str | None = None

    @model_validator(mode="after")
    def _khong_rong(self) -> "AttackExpect":
        if not self.model_dump(exclude_none=True):
            raise ValueError("expect phải có ít nhất một kỳ vọng")
        return self


class AttackCase(_Row):
    id: Annotated[str, Field(pattern=r"^AT\d{2,3}$")]
    type: AttackType
    channel: Literal["text", "voice"]
    input: NonBlank
    meta: dict[str, float | str | bool] | None = None
    repeat_all_turns: bool = False
    expect: AttackExpect


# ---------- judge/labeled.jsonl (KT-04, C1-16) ----------


class LabeledExplanation(_Row):
    id: Annotated[str, Field(pattern=r"^J\d{3}$")]
    node: Annotated[str, Field(pattern=r"^N\d+$")]
    transcript: NonBlank
    label: Verdict
    scores: dict[CriterionCode, Score]
    annotator: NonBlank
    source: Literal["human", "ai_draft"]  # ai_draft = nháp do AI soạn, chưa được người gán nhãn độc lập
    covered_points: list[str] = []
    missing_points: list[str] = []
    note: str | None = None

    @model_validator(mode="after")
    def _du_5_tieu_chi(self) -> "LabeledExplanation":
        if set(self.scores) != set(CriterionCode):
            thieu = sorted(set(CriterionCode) - set(self.scores))
            raise ValueError(f"scores phải đủ 5 tiêu chí, thiếu {thieu}")
        return self


# ---------- tutee/sessions.jsonl (KT-12) ----------


class TuteeTurn(_Row):
    role: Literal["student", "tutee"]
    text: NonBlank


class TuteeSession(_Row):
    id: Annotated[str, Field(pattern=r"^T\d{2,3}$")]
    node: Annotated[str, Field(pattern=r"^N\d+$")]
    turns: Annotated[list[TuteeTurn], Field(min_length=1)]
    leak_annotations: list[int] = []  # chỉ số lượt tutee bị đánh dấu lộ đáp án

    @model_validator(mode="after")
    def _chi_so_hop_le(self) -> "TuteeSession":
        for i in self.leak_annotations:
            if not 0 <= i < len(self.turns) or self.turns[i].role != "tutee":
                raise ValueError(f"leak_annotations[{i}] không trỏ tới lượt tutee")
        return self


# ---------- stt/manifest.jsonl (KT-10) ----------


class SttClip(_Row):
    id: Annotated[str, Field(pattern=r"^S\d{2,3}$")]
    file: Annotated[str, Field(pattern=r"^audio/[\w.-]+\.(webm|wav|mp3|m4a|ogg)$")]
    reference: NonBlank
    terms: Annotated[list[NonBlank], Field(min_length=1)]
    speaker: str | None = None
    consent: bool = False  # người nói đã đồng ý cho dùng giọng (README) – bắt buộc khi đã có file

    @model_validator(mode="after")
    def _thuat_ngu_nam_trong_cau(self) -> "SttClip":
        ref = self.reference.lower()
        lac = [t for t in self.terms if t.lower() not in ref]
        if lac:
            raise ValueError(f"thuật ngữ không có trong reference: {lac}")
        return self


# ---------- tree/<mã>.gold.json (KT-09) ----------


@dataclass
class GoldTree:
    name: str
    subject: str
    syllabus: str | None
    tree: TreeVersion
    aliases: dict[str, list[str]]


class _GoldMeta(_Row):
    subject: NonBlank
    syllabus: str | None = None
    aliases: dict[str, list[NonBlank]] = {}


def _aliases(model: type[BaseModel]) -> set[str]:
    return {f.alias or name for name, f in model.model_fields.items()}


GOLD_META_KEYS = {"_source", "subject", "syllabus", "aliases"}


def _unknown_gold_keys(data: dict) -> str | None:
    """Kiểm trường lạ sau khi TreeVersion đã kiểm kiểu, kể cả rubric lồng trong nút."""
    lac = set(data) - _aliases(TreeVersion) - GOLD_META_KEYS
    if lac:
        return f"trường lạ ở gốc: {sorted(lac)}"
    for kind, model in (("nodes", Node), ("edges", Edge)):
        for i, item in enumerate(data.get(kind) or []):
            lac = set(item) - _aliases(model) if isinstance(item, dict) else set()
            if lac:
                return f"{kind}.{i}: trường lạ {sorted(lac)}"
    for i, node in enumerate(data["nodes"]):
        rubric = node.get("rubric")
        if rubric is None:
            continue
        where = f"nodes.{i}.rubric"
        lac = set(rubric) - _aliases(Rubric)
        if lac:
            return f"{where}: trường lạ {sorted(lac)}"
        for kind, model in (
            ("keyPoints", KeyPointSchema),
            ("misconceptions", MisconceptionSchema),
            ("scenarios", ChallengeScenarioSchema),
        ):
            for j, item in enumerate(rubric.get(kind, [])):
                lac = set(item) - _aliases(model)
                if lac:
                    return f"{where}.{kind}.{j}: trường lạ {sorted(lac)}"
    return None


# ---------- Bộ đọc ----------


def _rel(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.name if path.parent.name == "" else f"{path.parent.name}/{path.name}"


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    loc = ".".join(str(p) for p in err["loc"])
    return f"{loc}: {err['msg']}" if loc else err["msg"]


M = TypeVar("M", bound=BaseModel)


def read_jsonl(path: Path, model: type[M]) -> list[M]:
    if not path.is_file():
        raise DatasetError(f"{_rel(path)}: không có file")
    rows: list[M] = []
    seen: dict[str, int] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise DatasetError(f"{_rel(path)}: không phải UTF-8 – {exc.reason}") from exc
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        where = f"{_rel(path)}:{lineno}"
        try:
            row = model.model_validate(json.loads(line))
        except json.JSONDecodeError as exc:
            raise DatasetError(f"{where}: JSON hỏng – {exc.msg}") from exc
        except ValidationError as exc:
            raise DatasetError(f"{where}: {_first_error(exc)}") from exc
        row_id = getattr(row, "id", None)
        if row_id is not None:
            if row_id in seen:
                raise DatasetError(f"{where}: id {row_id} trùng với dòng {seen[row_id]}")
            seen[row_id] = lineno
        rows.append(row)
    return rows


def seed_node_codes() -> set[str]:
    if not SEED_TREE.is_file():
        raise DatasetError(f"{_rel(SEED_TREE)}: không có cây mẫu để đối chiếu nút")
    data = json.loads(SEED_TREE.read_text(encoding="utf-8"))
    return {n["code"] for n in data["nodes"] if n.get("code")}


def load_guard(root: Path = EVALS) -> list[AttackCase]:
    return read_jsonl(root / "guard" / "attacks.jsonl", AttackCase)


def load_judge(root: Path = EVALS, node_codes: set[str] | None = None) -> list[LabeledExplanation]:
    path = root / "judge" / "labeled.jsonl"
    items = read_jsonl(path, LabeledExplanation)
    codes = seed_node_codes() if node_codes is None else node_codes
    for j in items:
        if j.node not in codes:
            raise DatasetError(f"{_rel(path)}: {j.id} – nút {j.node} không có trong cây mẫu seed/")
    return items


def load_tutee(root: Path = EVALS) -> list[TuteeSession]:
    return read_jsonl(root / "tutee" / "sessions.jsonl", TuteeSession)


def load_stt(root: Path = EVALS) -> list[SttClip]:
    return read_jsonl(root / "stt" / "manifest.jsonl", SttClip)


def load_tree(root: Path = EVALS) -> dict[str, GoldTree]:
    golds: dict[str, GoldTree] = {}
    folder = root / "tree"
    for path in sorted(folder.glob("*.gold.json")):
        where = _rel(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError as exc:
            raise DatasetError(f"{where}: không phải UTF-8 – {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise DatasetError(f"{where}:{exc.lineno}: JSON hỏng – {exc.msg}") from exc
        try:
            if not isinstance(data, dict):
                raise DatasetError(f"{where}: gốc phải là object JSON")
            tree = TreeVersion.model_validate(data)
            lac = _unknown_gold_keys(data)
            if lac:
                raise DatasetError(f"{where}: {lac}")
            meta = _GoldMeta.model_validate({k: data[k] for k in ("subject", "syllabus", "aliases") if k in data})
        except ValidationError as exc:
            raise DatasetError(f"{where}: {_first_error(exc)}") from exc
        keys = {n.key for n in tree.nodes}
        la = sorted(set(meta.aliases) - keys)
        if la:
            raise DatasetError(f"{where}: aliases cho nút không có trong cây: {la}")
        cycle = find_cycle(build_graph(tree))
        if cycle:
            raise DatasetError(f"{where}: cây chuẩn có chu trình ({' → '.join(cycle)})")
        name = path.name.removesuffix(".gold.json")
        golds[name] = GoldTree(name=name, subject=meta.subject, syllabus=meta.syllabus, tree=tree, aliases=meta.aliases)
    if not golds:
        raise DatasetError(f"{_rel(folder)}: không có file *.gold.json")
    return golds


LOADERS = {"guard": load_guard, "judge": load_judge, "tutee": load_tutee, "stt": load_stt, "tree": load_tree}
OPTIONAL = {"tutee": "KT-12"}  # bộ chưa đến lượt: thiếu file thì báo "chưa có", không lỗi


@dataclass
class SuiteResult:
    name: str
    ok: bool
    count: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str = ""


def check_suite(name: str, root: Path = EVALS) -> SuiteResult:
    """Đọc một bộ; lỗi schema → ok=False kèm `<file>:<dòng>`; thiếu so với chỉ tiêu → cảnh báo."""
    loader = LOADERS[name]
    if name in OPTIONAL and not any((root / name).glob("*.jsonl")):
        return SuiteResult(name, ok=True, warnings=[f"chưa có dữ liệu ({OPTIONAL[name]})"])
    try:
        data = loader(root)
    except DatasetError as exc:
        return SuiteResult(name, ok=False, error=str(exc))
    result = SuiteResult(name, ok=True, count=len(data))
    lo, hi = TARGETS[name]
    if result.count < lo or (hi is not None and result.count > hi):
        want = f"{lo}–{hi}" if hi else f"≥ {lo}"
        result.warnings.append(f"có {result.count} mẫu, chỉ tiêu Bảng 7.3: {want}")
    if name == "judge":
        drafts = sum(1 for j in data if j.source == "ai_draft")
        if drafts:
            result.warnings.append(f"{drafts} lời giảng là nháp AI – cần người gán nhãn độc lập trước khi tính κ")
    if name == "tree":
        no_syllabus = [g.name for g in data.values() if not g.syllabus or not (REPO / g.syllabus).is_file()]
        if no_syllabus:
            result.warnings.append(f"cây chuẩn chưa có giáo trình kèm: {', '.join(no_syllabus)}")
    if name == "stt":
        missing = [c.id for c in data if not (root / "stt" / c.file).is_file()]
        if missing:
            result.warnings.append(f"chưa có file ghi âm: {', '.join(missing)}")
        no_consent = [c.id for c in data if (root / "stt" / c.file).is_file() and not c.consent]
        if no_consent:
            result.warnings.append(f"có file nhưng chưa ghi consent=true: {', '.join(no_consent)}")
    return result


def check_all(root: Path = EVALS) -> dict[str, SuiteResult]:
    return {name: check_suite(name, root) for name in LOADERS}
