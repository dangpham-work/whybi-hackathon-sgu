"""Chế độ demo (Bảng 7.4). Chủ: Đăng (C1-13).

`DEMO_MODE=1`: vẫn gọi LLM bình thường; chỉ khi LLM không dùng được (`AppError 503 LLM_UNAVAILABLE`, hết cả model dự
phòng) thì Tutee, Judge và bước dựng cây chuyển sang nội dung lưu sẵn để kịch bản demo chạy trọn khi mất mạng:
- Tutee: câu mở đầu mẫu, câu hỏi lấy từ tình huống / câu gợi mở trong rubric (`fallback_question`).
- Độ bao phủ và Judge: đối chiếu từ khóa của lời SV với từng ý chính của rubric, rồi áp BR-03 như thường.
- Cây: cây mẫu CTDL&GT kèm rubric trong `seed/` (GV vẫn phải duyệt trước khi phát hành).
Hàm ở đây thuần (không mạng, không CSDL); nơi gọi quyết định có dùng hay không bằng `active(exc)`.
"""

import re
import unicodedata

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.enums import CriterionCode
from app.models.schemas.session import CriterionScore, JudgeResult
from app.models.schemas.tree import Rubric

MATCH_RATIO = 0.4  # ≥ 40% từ khóa của một ý chính xuất hiện trong lời SV ⇒ coi là đã nêu
MIN_ANSWER_HITS = 2  # câu trả lời phản biện có ≥ 2 từ khóa của rubric ⇒ coi là vượt
CLEAR_MIN_WORDS = 40  # lời giảng đủ dài thì tiêu chí Rõ ràng đạt mức cao hơn

_STOP = frozenset(
    "la va cua mot cac co duoc cho trong khi de nhu the nay do voi thi se bang tu hay khong nhung cung rat "
    "vao ra tren duoi neu thay vi nen can phai moi ma".split()
)
_STUDENT_LINE = re.compile(r"^\[SV\]\s?(.*)$", re.M)
TIMEOUT_MARK = "hết giờ"


def active(exc: BaseException) -> bool:
    """Có nên dùng nội dung lưu sẵn cho lỗi này không: DEMO_MODE bật và LLM thật sự hết đường (503)."""
    return get_settings().demo_mode and isinstance(exc, AppError) and exc.code == "LLM_UNAVAILABLE"


def words(text: str) -> set[str]:
    """Từ khóa: bỏ dấu, chữ thường, bỏ từ nối ngắn."""
    plain = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    plain = "".join(c for c in plain if unicodedata.category(c) != "Mn")
    return {w for w in re.findall(r"[a-z0-9]+", plain) if len(w) >= 3 and w not in _STOP}


def covered_points(student_text: str, rubric: Rubric) -> list[str]:
    have = words(student_text)
    out = []
    for kp in rubric.key_points:
        need = words(kp.content)
        if need and len(need & have) / len(need) >= MATCH_RATIO:
            out.append(kp.id)
    return out


def student_lines(transcript_text: str) -> list[str]:
    lines = [m.strip() for m in _STUDENT_LINE.findall(transcript_text)]
    return lines if lines else [transcript_text.strip()]


def judge_result(transcript_text: str, rubric: Rubric, challenges_total: int | None) -> JudgeResult:
    """Chấm bằng từ khóa. Lời giảng đầu tiên + các câu trả lời đều được tính cho độ bao phủ; câu trả lời được tính là
    vượt phản biện khi chứa ≥ MIN_ANSWER_HITS từ khóa của rubric (câu hết giờ thì không)."""
    lines = student_lines(transcript_text)
    answers = [t for t in lines[1:] if TIMEOUT_MARK not in t.lower()]
    covered = covered_points(" ".join(lines), rubric)
    required = [k.id for k in rubric.key_points if k.is_required]
    ratio = sum(1 for k in required if k in covered) / len(required) if required else 1.0
    rubric_words = set().union(*(words(k.content) for k in rubric.key_points)) if rubric.key_points else set()
    passed = sum(1 for a in answers if len(words(a) & rubric_words) >= MIN_ANSWER_HITS)
    total = challenges_total if challenges_total is not None else len(lines[1:])
    passed = min(passed, total)
    n_words = sum(len(t.split()) for t in lines)
    scores = {
        CriterionCode.CORRECTNESS: round(min(100.0, 100 * ratio + 20), 1),  # không phát hiện lỗi sai bằng từ khóa
        CriterionCode.COVERAGE: round(100 * ratio, 1),
        CriterionCode.ESSENCE: round(100 * ratio * 0.9, 1),
        CriterionCode.ROBUSTNESS: round(100 * passed / total, 1) if total else 0.0,
        CriterionCode.CLARITY: 80.0 if n_words >= CLEAR_MIN_WORDS else 55.0,
    }
    first_covered = next((k.content for k in rubric.key_points if k.id in covered), None)
    return JudgeResult(
        criteria=[
            CriterionScore(code=c, score=scores[c], rationale="Chấm dự phòng (chế độ demo): đối chiếu từ khóa")
            for c in CriterionCode
        ],
        covered_points=covered,
        missing_points=[k.id for k in rubric.key_points if k.id not in covered],
        misconceptions=[],
        passed_challenges=passed,
        total_challenges=total,
        strengths=[f"Bạn đã nêu được: {first_covered}"] if first_covered else [],
        review_hints=["Thử nghĩ xem còn tình huống nào làm cách hiểu của bạn không còn đúng?"] if ratio < 1 else [],
        judge_runs=1,
    )


def seed_tree():
    """Cây mẫu CTDL&GT kèm rubric (bản sao để sửa được). Import trong hàm: tránh vòng import với services."""
    from app.services.skill_tree import load_seed_tree

    return load_seed_tree().model_copy(deep=True)


def seed_rubric(node_key: str) -> Rubric | None:
    """Rubric lưu sẵn của nút cùng `key` trong cây mẫu (chưa duyệt), hoặc None nếu cây mẫu không có nút đó."""
    node = next((n for n in seed_tree().nodes if n.key == node_key and n.rubric), None)
    return node.rubric.model_copy(update={"approved": False}) if node else None
