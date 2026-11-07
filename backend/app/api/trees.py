"""API cây kỹ năng theo Bảng 5.10 – FR-SK-04…10. Chủ: Long (C2-02, C2-09, C2-10, C2-16), Đăng (C1-11)."""

from uuid import UUID

from fastapi import APIRouter

from app.api.deps import CurrentUser, Lecturer, LecturerOrStudent, Student
from app.core.errors import NotImplementedYet
from app.models.schemas.tree import Edge, Node, Rubric, TreeVersion
from app.services.skill_tree import SkillTreeService

router = APIRouter(tags=["trees"])


@router.get("/classes/{class_id}/tree", response_model=TreeVersion)
def get_tree(class_id: UUID, draft: bool = False, user: CurrentUser = LecturerOrStudent) -> TreeVersion:
    """Cây đang phát hành (hoặc bản nháp với GV). C2-02: đọc cây mẫu qua SkillTreeService, chưa dùng CSDL."""
    return SkillTreeService().get_class_tree(class_id, draft=draft)


@router.post("/tree-versions/{version_id}/nodes", response_model=Node, status_code=201)
def add_node(version_id: UUID, body: Node, user: CurrentUser = Lecturer) -> Node:
    raise NotImplementedYet("C2-09")


@router.patch("/nodes/{node_id}", response_model=Node)
def update_node(node_id: UUID, body: Node, user: CurrentUser = Lecturer) -> Node:
    """Sửa nút / vị trí kéo thả."""
    raise NotImplementedYet("C2-09")


@router.post("/tree-versions/{version_id}/edges", response_model=Edge, status_code=201)
def add_edge(version_id: UUID, body: Edge, user: CurrentUser = Lecturer) -> Edge:
    """Kiểm tra chu trình trước khi ghi; tạo chu trình ⇒ 409 CYCLE_DETECTED kèm đường đi (TC03)."""
    raise NotImplementedYet("C2-09")


@router.delete("/edges/{edge_id}", status_code=204)
def delete_edge(edge_id: UUID, user: CurrentUser = Lecturer) -> None:
    raise NotImplementedYet("C2-09")


@router.put("/nodes/{node_id}/rubric", response_model=Rubric)
def put_rubric(node_id: UUID, body: Rubric, user: CurrentUser = Lecturer) -> Rubric:
    """Sửa / duyệt rubric (FR-SK-08)."""
    raise NotImplementedYet("C2-09")


@router.post("/nodes/{node_id}/rubric/regenerate", response_model=Rubric)
def regenerate_rubric(node_id: UUID, user: CurrentUser = Lecturer) -> Rubric:
    """Sinh lại rubric bằng AI (RAG) – thẻ của Đăng."""
    raise NotImplementedYet("C1-11")


@router.post("/tree-versions/{version_id}/publish", response_model=TreeVersion)
def publish(version_id: UUID, user: CurrentUser = Lecturer) -> TreeVersion:
    """Kiểm BR-05; khởi tạo / di chuyển trạng thái SV theo BR-14 (TC04, TC05)."""
    raise NotImplementedYet("C2-09")


@router.get("/classes/{class_id}/tree-versions", response_model=list[TreeVersion])
def list_versions(class_id: UUID, user: CurrentUser = Lecturer) -> list[TreeVersion]:
    """Lịch sử phiên bản (FR-SK-10, vòng 2)."""
    raise NotImplementedYet("C2-16")


@router.post("/tree-versions/{version_id}/restore", response_model=TreeVersion, status_code=201)
def restore_version(version_id: UUID, user: CurrentUser = Lecturer) -> TreeVersion:
    """Khôi phục phiên bản cũ thành bản nháp mới (FR-SK-10)."""
    raise NotImplementedYet("C2-16")


@router.get("/classes/{class_id}/my-map", response_model=TreeVersion)
def my_map(class_id: UUID, user: CurrentUser = Student) -> TreeVersion:
    """Bản đồ học tập cá nhân: cây + trạng thái từng nút của SV (FR-TB-01)."""
    raise NotImplementedYet("C2-10")
