"""Chỉ số cho bộ đánh giá (Bảng 7.3): Cohen's κ, ma trận nhầm lẫn, tỉ lệ. Hàm thuần, không phụ thuộc backend.
Chủ: Đăng (C1-16, C1-17)."""

from collections import Counter
from collections.abc import Sequence


def confusion(truth: Sequence[str], pred: Sequence[str], labels: Sequence[str]) -> dict[str, dict[str, int]]:
    """matrix[nhãn thật][nhãn dự đoán] = số mẫu."""
    if len(truth) != len(pred):
        raise ValueError("truth và pred phải cùng độ dài")
    m = {t: dict.fromkeys(labels, 0) for t in labels}
    for t, p in zip(truth, pred, strict=True):
        m[t][p] += 1
    return m


def cohen_kappa(truth: Sequence[str], pred: Sequence[str]) -> float:
    """κ = (po − pe) / (1 − pe). Hai bên cùng chỉ có một nhãn duy nhất (pe = 1) ⇒ 1.0 nếu trùng hết, ngược lại 0.0."""
    n = len(truth)
    if n == 0 or n != len(pred):
        raise ValueError("cần ≥ 1 mẫu và truth, pred cùng độ dài")
    po = sum(t == p for t, p in zip(truth, pred, strict=True)) / n
    ct, cp = Counter(truth), Counter(pred)
    pe = sum(ct[k] * cp[k] for k in set(ct) | set(cp)) / (n * n)
    if pe == 1:
        return 1.0 if po == 1 else 0.0
    return (po - pe) / (1 - pe)


def accuracy(truth: Sequence[str], pred: Sequence[str]) -> float:
    return sum(t == p for t, p in zip(truth, pred, strict=True)) / len(truth)


def rate(num: int, den: int) -> float:
    """num/den, 0 khi den = 0 (không có mẫu thì không có tỉ lệ vi phạm)."""
    return num / den if den else 0.0


def mean_abs_error(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(abs(x - y) for x, y in zip(a, b, strict=True)) / len(a)


def format_confusion(m: dict[str, dict[str, int]]) -> str:
    """Bảng Markdown: hàng = nhãn thật, cột = Judge dự đoán."""
    labels = list(m)
    lines = ["| thật \\ Judge | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    lines += [f"| {t} | " + " | ".join(str(m[t][p]) for p in labels) + " |" for t in labels]
    return "\n".join(lines)
