"""Chạy bộ đánh giá: `uv run python ../evals/run.py <guard|judge|tree|tutee|stt>` (từ thư mục backend).

Khung KT-04 / KT-07 / KT-09 / KT-10 / KT-12 – mỗi bộ đọc dữ liệu trong evals/<bộ>/ và ghi results/<bộ>.md.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


sys.stdout.reconfigure(encoding="utf-8")  # console Windows


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_guard() -> None:
    attacks = load_jsonl(ROOT / "guard" / "attacks.jsonl")
    print(f"{len(attacks)} kịch bản tấn công (cần ≥ 50) – KT-07: gọi Guard/Tutee/Judge và so với 'expect'.")
    raise NotImplementedError("KT-07")


SUITES = {"guard": run_guard}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in SUITES:
        sys.exit(f"Dùng: run.py <{'|'.join(SUITES)}> (các bộ khác: thêm hàm run_<bộ> – thẻ KT tương ứng)")
    SUITES[name]()
