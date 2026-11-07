"""Nạp dữ liệu mẫu seed/ vào CSDL (C2-02 / KT-02): tài khoản, lớp CTDL&GT – Nhóm 02, cây mẫu 11 nút.

    cd backend && uv run python ../scripts/seed_db.py

Chạy lại an toàn: bỏ qua bản ghi đã có (theo email, mã lớp, tên cây).
"""

import json
import sys
from pathlib import Path

SEED = Path(__file__).resolve().parent.parent / "seed"


sys.stdout.reconfigure(encoding="utf-8")  # console Windows


def main() -> None:
    users = json.loads((SEED / "users.json").read_text(encoding="utf-8"))
    klass = json.loads((SEED / "class.json").read_text(encoding="utf-8"))
    tree = json.loads((SEED / "tree_ctdl_gt.json").read_text(encoding="utf-8"))
    print(
        f"{len(users['lecturers'])} GV, {len(users['admins'])} QTV, {len(users['students'])} SV;"
        f" lớp {klass['class']['join_code']}; cây {len(tree['nodes'])} nút / {len(tree['edges'])} cạnh"
    )
    # TODO C2-02: mở app.db.session, băm mật khẩu bằng app.core.security, upsert users → lecturers/students,
    #   courses → class_sections → enrollments,
    #   skill_trees → tree_versions → concept_nodes / prerequisite_edges / rubrics.
    raise NotImplementedError("C2-02")


if __name__ == "__main__":
    main()
