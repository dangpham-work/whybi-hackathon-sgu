"""KT-05 – giả lập N sinh viên giảng bài để bản đồ nhiệt đổi màu thật (demo đoạn MX3, kế hoạch Bảng 18).

Gửi kết quả qua ĐÚNG API phiên (không ghi thẳng CSDL – kế hoạch §3.2), backend nên chạy LLM_MODE=fake.

    python scripts/simulate_students.py --base http://localhost --class CTDL2026 --students 30 --pass-rate 0.6
"""

import argparse
import json
import sys
from pathlib import Path

SEED = Path(__file__).resolve().parent.parent / "seed"


sys.stdout.reconfigure(encoding="utf-8")  # console Windows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost")
    ap.add_argument("--class", dest="join_code", default="CTDL2026")
    ap.add_argument("--students", type=int, default=30)
    ap.add_argument("--pass-rate", type=float, default=0.6)
    ap.add_argument("--weak-node", default="N5", help="Nút cố tình cho nhiều SV trượt (điểm nghẽn gốc)")
    ap.add_argument("--delay", type=float, default=0.3, help="Giây giữa các SV để thấy bản đồ đổi dần")
    args = ap.parse_args()

    students = json.loads((SEED / "users.json").read_text(encoding="utf-8"))["students"][: args.students]
    print(f"Giả lập {len(students)} SV vào lớp {args.join_code} tại {args.base}")
    # TODO KT-05: với mỗi SV – POST /api/v1/auth/login → POST /classes/join → chọn nút trên Biên
    #   → POST /sessions → các lượt /turns (văn bản mẫu Đạt/Chưa đạt theo pass-rate, weak-node trượt nhiều)
    #   → POST /sessions/{id}/complete. Dùng urllib hoặc httpx; in tiến độ từng SV.
    raise NotImplementedError("KT-05")


if __name__ == "__main__":
    main()
