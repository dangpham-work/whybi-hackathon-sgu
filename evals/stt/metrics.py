"""KT-10: WER theo token cách trắng; không bỏ dấu tiếng Việt hoặc chặn WER ở 100%."""

import math
import unicodedata


def tokens(text: str) -> list[str]:
    if not isinstance(text, str):
        raise ValueError("text phải là chuỗi")
    text = unicodedata.normalize("NFKC", text).casefold()
    return "".join(" " if unicodedata.category(c).startswith("P") else c for c in text).split()


def _align(reference, hypothesis):
    ref, hyp = tokens(reference), tokens(hypothesis)
    if not ref:
        raise ValueError("reference không được rỗng sau chuẩn hóa")
    table = [list(range(len(hyp) + 1))]
    for i, expected in enumerate(ref, 1):
        row = [i]
        for j, actual in enumerate(hyp, 1):
            row.append(min(table[i - 1][j - 1] + (expected != actual), table[i - 1][j] + 1, row[j - 1] + 1))
        table.append(row)
    i, j = len(ref), len(hyp)
    substitutions = deletions = insertions = 0
    matches = {}
    # Hòa điểm: ưu tiên đường chéo, rồi xóa, rồi chèn; cố định để đếm thuật ngữ tái lập được.
    while i or j:
        if i and j and table[i][j] == table[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            if ref[i - 1] == hyp[j - 1]:
                matches[i - 1] = j - 1
            else:
                substitutions += 1
            i, j = i - 1, j - 1
        elif i and table[i][j] == table[i - 1][j] + 1:
            deletions += 1
            i -= 1
        else:
            insertions += 1
            j -= 1
    counts = {
        "reference_words": len(ref),
        "substitutions": substitutions,
        "deletions": deletions,
        "insertions": insertions,
        "wer": (substitutions + deletions + insertions) / len(ref),
    }
    return counts, ref, matches


def word_errors(reference: str, hypothesis: str) -> dict:
    return _align(reference, hypothesis)[0]


def term_accuracy(reference: str, hypothesis: str, terms: list[str]) -> dict:
    """Đếm lần xuất hiện thuật ngữ khớp nguyên cụm trên căn chỉnh WER, không tìm chuỗi con."""
    _, ref, matched = _align(reference, hypothesis)
    phrases = [tokens(term) for term in terms]
    if not phrases or any(not p for p in phrases) or len({tuple(p) for p in phrases}) != len(phrases):
        raise ValueError("terms phải khác nhau và không rỗng sau chuẩn hóa")
    correct = total = 0
    for phrase in phrases:
        starts = [i for i in range(len(ref) - len(phrase) + 1) if ref[i : i + len(phrase)] == phrase]
        if not starts:
            raise ValueError("thuật ngữ không có nguyên cụm trong reference")
        for start in starts:
            positions = [matched.get(i) for i in range(start, start + len(phrase))]
            total += 1
            correct += positions[0] is not None and positions == list(range(positions[0], positions[0] + len(phrase)))
    return {"correct": correct, "total": total, "accuracy": correct / total}


def corpus_wer(scores: list[dict]) -> float | None:
    errors = words = 0
    for row in scores:
        counts = [row[k] for k in ("reference_words", "substitutions", "deletions", "insertions")]
        if any(type(n) is not int or n < 0 for n in counts) or not counts[0]:
            raise ValueError("số đếm WER không hợp lệ")
        words += counts[0]
        errors += sum(counts[1:])
    return errors / words if words else None


def p95(seconds: list[float]) -> float | None:
    """Nearest rank: phần tử ceil(0.95*n), mỗi lượt chạy có cùng trọng số."""
    if any(type(s) not in {int, float} or not math.isfinite(s) or s < 0 for s in seconds):
        raise ValueError("độ trễ phải là số hữu hạn không âm")
    return sorted(seconds)[math.ceil(0.95 * len(seconds)) - 1] if seconds else None
