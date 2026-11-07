"""Sinh rubric cho nút của cây (FR-SK-05, FR-SK-08): ghép RetrievalService (RAG) với RubricGenerator.
Chủ: Đăng (C1-11)."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.ai import demo
from app.ai.agents.rubric_generator import TOP_PASSAGES, RubricGenerator, class_params, query_for
from app.ai.gateway import LLMGateway, get_gateway
from app.core.errors import AppError
from app.models.schemas.tree import Node, Rubric
from app.models.users import ClassSection
from app.services.retrieval import RetrievalService


def generate_rubric(db: Session, class_id: UUID, node: Node, gateway: LLMGateway | None = None) -> Rubric:
    """Rubric chưa duyệt cho `node`, dựa trên các đoạn giáo trình gần nhất của lớp; ngưỡng Đạt và số câu phản biện lấy
    từ cấu hình lớp (C2-17)."""
    gw = gateway or get_gateway()
    passages = RetrievalService(db, gw).retrieve(class_id, query_for(node), TOP_PASSAGES)
    return RubricGenerator(gw, **class_params(db.get(ClassSection, class_id))).generate(node, passages)


def regenerate_rubric_for_node(trees, node_id: UUID, user) -> Rubric:
    """POST /nodes/{id}/rubric/regenerate: kiểm quyền → sinh (chờ LLM, không giữ khóa) → ghi đè, về trạng thái nháp."""
    class_id, node = trees.node_for_edit(node_id, user)
    trees.db.rollback()  # kết thúc giao dịch đọc trước khi chờ LLM
    try:
        rubric = generate_rubric(trees.db, class_id, node)
    except AppError as exc:
        saved = demo.seed_rubric(node.key) if demo.active(exc) else None
        if saved is None:
            raise
        rubric = saved  # C1-13: LLM mất kết nối ⇒ rubric lưu sẵn của cây mẫu
    return trees.put_rubric(node_id, rubric, user)
