"""API cây kỹ năng theo Bảng 5.10 – FR-SK-04…10. Chủ: Long (C2-02, C2-09, C2-10, C2-16), Đăng (C1-11)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, Lecturer, LecturerOrStudent, Student
from app.db.session import get_db
from app.models.schemas.mastery import MyMap
from app.models.schemas.tree import Edge, Node, NodePatch, Rubric, TreeDiff, TreeVersion
from app.services.mastery import MasteryService
from app.services.rubric import regenerate_rubric_for_node
from app.services.skill_tree import SkillTreeService

router = APIRouter(tags=["trees"])


def get_tree_service(db: Session = Depends(get_db)) -> SkillTreeService:
    return SkillTreeService(db)


Trees = Annotated[SkillTreeService, Depends(get_tree_service)]


@router.get("/classes/{class_id}/tree", response_model=TreeVersion)
def get_tree(class_id: UUID, trees: Trees, draft: bool = False, user: CurrentUser = LecturerOrStudent) -> TreeVersion:
    """Cây đang phát hành của lớp; GV phụ trách gửi `draft=true` để lấy phiên bản mới nhất (kể cả nháp).
    SV phải đã tham gia lớp. Lớp mẫu SEED_CLASS_ID chưa có trong CSDL ⇒ trả cây từ seed/ (C2-02)."""
    return trees.get_class_tree(class_id, user=user, draft=draft)


@router.post("/classes/{class_id}/tree-versions", response_model=TreeVersion, status_code=201)
def create_version(
    class_id: UUID,
    trees: Trees,
    body: Annotated[TreeVersion | None, Body()] = None,
    sanitize: bool = False,
    user: CurrentUser = Lecturer,
) -> TreeVersion:
    """Tạo bản nháp mới (C2-09). Có body: nhập cây (nút, cạnh theo key, rubric) – `sanitize=true` chạy hậu xử lý
    6.1.4 (phá chu trình, rút gọn bắc cầu), không sanitize mà có chu trình ⇒ 409 CYCLE_DETECTED.
    Không body: sao bản đang phát hành để sửa tiếp."""
    return trees.create_version(class_id, user, body, sanitize_graph=sanitize)


@router.post("/tree-versions/{version_id}/nodes", response_model=Node, status_code=201)
def add_node(version_id: UUID, body: Node, trees: Trees, user: CurrentUser = Lecturer) -> Node:
    """Key trùng trong phiên bản ⇒ 409 NODE_KEY_EXISTS. Chỉ sửa được bản DRAFT / EDITING (409 VERSION_NOT_EDITABLE)."""
    return trees.add_node(version_id, body, user)


@router.patch("/nodes/{node_id}", response_model=Node)
def update_node(node_id: UUID, body: NodePatch, trees: Trees, user: CurrentUser = Lecturer) -> Node:
    """Sửa nút / vị trí kéo thả – chỉ gửi trường cần đổi."""
    return trees.update_node(node_id, body, user)


@router.post("/tree-versions/{version_id}/edges", response_model=Edge, status_code=201)
def add_edge(version_id: UUID, body: Edge, trees: Trees, user: CurrentUser = Lecturer) -> Edge:
    """Kiểm tra chu trình trước khi ghi; tạo chu trình ⇒ 409 CYCLE_DETECTED kèm `details.path` (TC03).
    Cạnh đã có ⇒ 409 EDGE_EXISTS; key lạ ⇒ 404 NODE_NOT_FOUND."""
    return trees.add_edge(version_id, body, user)


@router.delete("/edges/{edge_id}", status_code=204)
def delete_edge(edge_id: UUID, trees: Trees, user: CurrentUser = Lecturer) -> None:
    trees.delete_edge(edge_id, user)


@router.put("/nodes/{node_id}/rubric", response_model=Rubric)
def put_rubric(node_id: UUID, body: Rubric, trees: Trees, user: CurrentUser = Lecturer) -> Rubric:
    """Sửa / duyệt rubric (FR-SK-08): `approved=true` là duyệt."""
    return trees.put_rubric(node_id, body, user)


@router.post("/nodes/{node_id}/rubric/regenerate", response_model=Rubric)
def regenerate_rubric(node_id: UUID, trees: Trees, user: CurrentUser = Lecturer) -> Rubric:
    """Sinh lại rubric bằng AI (RAG) cho một nút; kết quả về trạng thái chưa duyệt (FR-SK-08)."""
    return regenerate_rubric_for_node(trees, node_id, user)


@router.post("/tree-versions/{version_id}/publish", response_model=TreeVersion)
def publish(version_id: UUID, trees: Trees, user: CurrentUser = Lecturer) -> TreeVersion:
    """Kiểm BR-05 (DAG, có nút gốc, mọi rubric đã duyệt) – thiếu ⇒ 422 PUBLISH_CHECK_FAILED kèm `details.errors`.
    Bản phát hành trước chuyển ARCHIVED. Khởi tạo / di chuyển trạng thái SV (BR-14): C2-10."""
    return trees.publish(version_id, user)


@router.get("/classes/{class_id}/tree-versions", response_model=list[TreeVersion])
def list_versions(class_id: UUID, trees: Trees, user: CurrentUser = Lecturer) -> list[TreeVersion]:
    """Lịch sử phiên bản, mới nhất trước (FR-SK-10)."""
    return trees.list_versions(class_id, user)


@router.post("/tree-versions/{version_id}/restore", response_model=TreeVersion, status_code=201)
def restore_version(version_id: UUID, trees: Trees, user: CurrentUser = Lecturer) -> TreeVersion:
    """Khôi phục phiên bản cũ thành bản nháp mới (FR-SK-10); bản cũ giữ nguyên, rubric duyệt lại."""
    return trees.restore_version(version_id, user)


@router.get("/tree-versions/{from_id}/compare/{to_id}", response_model=TreeDiff)
def compare_versions(from_id: UUID, to_id: UUID, trees: Trees, user: CurrentUser = Lecturer) -> TreeDiff:
    """So sánh hai phiên bản cùng lớp theo key nút: thêm, bỏ, đổi; cạnh thêm, bỏ (FR-SK-10)."""
    return trees.compare_versions(from_id, to_id, user)


@router.get("/classes/{class_id}/my-map", response_model=MyMap)
def my_map(class_id: UUID, db: Session = Depends(get_db), user: CurrentUser = Student) -> MyMap:
    """Bản đồ học tập cá nhân (FR-TB-01, SV-02 / SV-03): cây đang phát hành + trạng thái, điểm cao nhất, số lượt,
    tiên quyết còn thiếu, giờ được thử lại của từng nút.
    Lỗi: 403 NOT_ENROLLED, 404 CLASS_NOT_FOUND / TREE_NOT_PUBLISHED."""
    return MasteryService(db).my_map(class_id, user.id)
