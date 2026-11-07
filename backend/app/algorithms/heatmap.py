"""Chỉ số nút và quy tắc phân màu bản đồ nhiệt (mục 6.5.1–6.5.2, Bảng 6.6, BR-06). Chủ: Long (C2-11).

Hàm thuần, không I/O – HeatmapService đọc cột ma trận rồi gọi `aggregate`.

- Đã thử: SV đã có kết quả tại nút (attempts > 0, hoặc trạng thái là kết quả: Đạt / Chưa đạt / Cần xác nhận lại).
- Đạt: MASTERED hoặc NEEDS_REVERIFY (như MasteryService khi xét tiên quyết – BR-02).
- IN_PROGRESS: xét theo trạng thái trước phiên (`prev_state`) – đang giảng lại không xóa kết quả cũ.
- a(n) = đã thử / sĩ số; p(n) = Đạt / đã thử (chỉ tính trên số đã thử – tách "chưa thử" khỏi "chưa đạt").
- Màu: đã thử < cỡ mẫu tối thiểu ⇒ XÁM; p ≥ green ⇒ XANH; p ≥ yellow ⇒ VÀNG; còn lại ⇒ ĐỎ.
  So sánh bằng phân số đúng (21/30 = 70% là XANH, không lệch do số thực).
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from fractions import Fraction

from app.models.enums import HeatColor, HeatSample, MasteryState

S = MasteryState
PASSED_STATES = frozenset({S.MASTERED, S.NEEDS_REVERIFY})
RESULT_STATES = frozenset({S.MASTERED, S.NOT_PASSED, S.NEEDS_REVERIFY})

DEFAULT_GREEN = 0.7
DEFAULT_YELLOW = 0.4
DEFAULT_MIN_SAMPLE = 5


@dataclass(frozen=True)
class ColorRule:
    """Ngưỡng màu của lớp (mặc định Bảng 6.6; GV cấu hình được – class_sections.color_thresholds, min_sample)."""

    green: float = DEFAULT_GREEN
    yellow: float = DEFAULT_YELLOW
    min_sample: int = DEFAULT_MIN_SAMPLE

    def __post_init__(self) -> None:
        if not 0 <= self.yellow <= self.green <= 1:
            raise ValueError(f"ngưỡng màu phải thỏa 0 ≤ yellow ≤ green ≤ 1 (yellow={self.yellow}, green={self.green})")
        if self.min_sample < 1:
            raise ValueError(f"cỡ mẫu tối thiểu phải ≥ 1 (min_sample={self.min_sample})")

    @classmethod
    def from_class(cls, color_thresholds: Mapping | None, min_sample: int | None) -> "ColorRule":
        t = color_thresholds or {}
        return cls(
            green=float(t.get("green", DEFAULT_GREEN)),
            yellow=float(t.get("yellow", DEFAULT_YELLOW)),
            min_sample=DEFAULT_MIN_SAMPLE if min_sample is None else int(min_sample),
        )


@dataclass(frozen=True)
class Cell:
    """Một ô M[SV, nút] cần cho tổng hợp."""

    state: MasteryState
    attempts: int = 0
    prev_state: MasteryState | None = None  # chỉ dùng khi state = IN_PROGRESS

    @property
    def effective_state(self) -> MasteryState:
        if self.state == S.IN_PROGRESS:
            return self.prev_state or S.AVAILABLE
        return self.state

    @property
    def attempted(self) -> bool:
        return self.attempts > 0 or self.effective_state in RESULT_STATES

    @property
    def passed(self) -> bool:
        return self.effective_state in PASSED_STATES


@dataclass(frozen=True)
class NodeStat:
    """Chỉ số một nút (một dòng class_node_stats)."""

    enrolled: int
    attempted: int
    passed: int
    pass_rate: float | None  # None khi chưa ai thử
    attempted_rate: float
    avg_attempts: float | None  # trung bình lượt trên SV đã thử
    color: HeatColor
    sample: HeatSample
    label: str  # nhãn chữ đi kèm màu (màu không bao giờ đứng một mình)


def classify(attempted: int, passed: int, rule: ColorRule) -> tuple[HeatColor, HeatSample]:
    """Bảng 6.6. XÁM chỉ vì thiếu mẫu, không bao giờ vì tỉ lệ thấp."""
    if attempted <= 0:
        return HeatColor.GREY, HeatSample.NO_ATTEMPT
    if attempted < rule.min_sample:
        return HeatColor.GREY, HeatSample.INSUFFICIENT
    p = Fraction(passed, attempted)
    if p >= Fraction(str(rule.green)):
        return HeatColor.GREEN, HeatSample.SUFFICIENT
    if p >= Fraction(str(rule.yellow)):
        return HeatColor.YELLOW, HeatSample.SUFFICIENT
    return HeatColor.RED, HeatSample.SUFFICIENT


def label(color: HeatColor, sample: HeatSample, attempted: int, passed: int, rule: ColorRule) -> str:
    if sample == HeatSample.NO_ATTEMPT:
        return "Chưa có SV nào thử"
    if sample == HeatSample.INSUFFICIENT:
        return f"Chưa đủ mẫu ({attempted}/{rule.min_sample} SV đã thử)"
    ratio = f"{passed}/{attempted} Đạt"
    return {
        HeatColor.GREEN: f"✓ Lớp vững – {ratio}",
        HeatColor.YELLOW: f"! Cần chú ý – {ratio}",
        HeatColor.RED: f"✗ Điểm nghẽn – {ratio}",
    }[color]


def aggregate(cells: Iterable[Cell], enrolled: int, rule: ColorRule) -> NodeStat:
    """Tổng hợp một cột ma trận (các ô của SV đang ghi danh) thành chỉ số + màu."""
    tried = [c for c in cells if c.attempted]
    attempted = len(tried)
    passed = sum(1 for c in tried if c.passed)
    color, sample = classify(attempted, passed, rule)
    return NodeStat(
        enrolled=enrolled,
        attempted=attempted,
        passed=passed,
        pass_rate=passed / attempted if attempted else None,
        attempted_rate=attempted / enrolled if enrolled else 0.0,
        avg_attempts=sum(c.attempts for c in tried) / attempted if attempted else None,
        color=color,
        sample=sample,
        label=label(color, sample, attempted, passed, rule),
    )
