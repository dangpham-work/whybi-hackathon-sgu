"""SkillTreeService – Sinh cây nháp, sửa cây, duyệt rubric, phát hành (UC06–UC09). Chủ: Long (C2-02, C2-09),
Đăng (C1-10, C1-11).

C2-02 – đọc cây từ seed JSON, chưa có CSDL:
- Lớp mẫu duy nhất "CTDL&GT – Nhóm 02" có id cố định `SEED_CLASS_ID`. Cây lấy từ `seed/tree_ctdl_gt.json` (Quyền soạn).
- id của phiên bản, nút, cạnh sinh bằng uuid5 từ key nên ổn định giữa các lần gọi và giữa các máy.
- Hướng đi sau này:
  - C2-06 có bảng `skill_trees` / `tree_versions` / `concept_nodes` / `prerequisite_edges` / `rubrics`.
    Script `scripts/seed_db.py` nạp đúng tệp này vào CSDL, giữ nguyên các uuid5 ở đây.
  - C2-09 thay `get_class_tree` bằng truy vấn: phiên bản `published_version_id` của lớp, hoặc bản nháp mới nhất khi
    GV gọi `draft=true`.
  - Chữ ký `get_class_tree(class_id, draft) -> TreeVersion` giữ nguyên, router và bên dùng không phải đổi.
"""

import json
from functools import lru_cache
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from app.algorithms.dag import build_graph, find_cycle
from app.core.config import get_settings
from app.core.errors import AppError
from app.models.schemas.tree import TreeVersion

_NS = uuid5(NAMESPACE_URL, "https://whybi.ai/seed")
SEED_CLASS_ID = uuid5(_NS, "class/CTDL2026")
SEED_TREE_FILE = "tree_ctdl_gt.json"


def seed_dir() -> Path:
    configured = get_settings().seed_dir
    if configured:
        return Path(configured)
    # backend/app/services/skill_tree.py → gốc repo; trong image (/app/app/services) ra /seed
    return Path(__file__).resolve().parents[3] / "seed"


@lru_cache
def load_seed_tree() -> TreeVersion:
    """Đọc và kiểm cây mẫu một lần. Cây không phải DAG thì báo lỗi ngay, không trả cho client."""
    raw = json.loads((seed_dir() / SEED_TREE_FILE).read_text(encoding="utf-8"))
    tree = TreeVersion.model_validate(raw)
    version_no = tree.version_no
    tree.id = uuid5(_NS, f"class/CTDL2026/version/{version_no}")
    tree.class_id = SEED_CLASS_ID
    for n in tree.nodes:
        n.id = uuid5(_NS, f"version/{version_no}/node/{n.key}")
    for e in tree.edges:
        e.id = uuid5(_NS, f"version/{version_no}/edge/{e.from_key}->{e.to_key}")
    cycle = find_cycle(build_graph(tree))
    if cycle:
        raise ValueError(f"Cây mẫu {SEED_TREE_FILE} có chu trình: {' → '.join(cycle)}")
    return tree


class SkillTreeService:
    def get_class_tree(self, class_id: UUID, draft: bool = False) -> TreeVersion:
        """Cây của lớp (FR-SK-04). C2-02: chỉ lớp mẫu; seed chỉ có một phiên bản nên `draft` chưa có tác dụng."""
        if class_id != SEED_CLASS_ID:
            raise AppError(
                404, "CLASS_NOT_FOUND", "Không tìm thấy lớp hoặc lớp chưa có cây", {"classId": str(class_id)}
            )
        return load_seed_tree().model_copy(deep=True)

    def build_draft_tree(self, document_id):
        raise NotImplementedError("C1-10")

    def add_edge(self, version_id, from_key, to_key):
        raise NotImplementedError("C2-09")

    def approve_rubric(self, node_id, rubric):
        raise NotImplementedError("C2-09")

    def publish(self, version_id):
        raise NotImplementedError("C2-09")
