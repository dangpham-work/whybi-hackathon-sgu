"""Chạy bộ đánh giá: `uv run python ../evals/run.py <check|guard|judge|tree|tutee|stt>` (từ thư mục backend).

- `check` (KT-04): đọc mọi bộ trong evals/ theo schema `eval_datasets.py`, in số mẫu + cảnh báo; thoát 1 nếu có bộ hỏng.
- Các bộ còn lại: khung KT-07 / KT-09 / KT-10 / KT-12: đọc qua `eval_datasets.py`, ghi results/<bộ>.md.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")  # console Windows

import eval_datasets as datasets  # noqa: E402


def run_check(root: Path = datasets.EVALS) -> None:
    report = datasets.check_all(root)
    for r in report.values():
        mark = "OK " if r.ok else "LỖI"
        print(f"[{mark}] {r.name:<6} {r.count:>4} mẫu" + (f" – {r.error}" if r.error else ""))
        for w in r.warnings:
            print(f"        ! {w}")
    if not all(r.ok for r in report.values()):
        sys.exit(1)


def run_guard() -> None:
    attacks = datasets.load_guard()
    print(f"{len(attacks)} kịch bản tấn công (cần ≥ 50) – KT-07: gọi Guard/Tutee/Judge và so với 'expect'.")
    raise NotImplementedError("KT-07")


SUITES = {"check": run_check, "guard": run_guard}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in SUITES:
        sys.exit(f"Dùng: run.py <{'|'.join(SUITES)}> (các bộ khác: thêm hàm run_<bộ> – thẻ KT tương ứng)")
    SUITES[name]()
