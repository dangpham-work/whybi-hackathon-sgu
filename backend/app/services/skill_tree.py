"""SkillTreeService – nhập cây nháp, sửa cây, duyệt rubric, phát hành (UC06–UC09, Bảng 5.10).
Chủ: Long (C2-02, C2-09), Đăng (C1-10, C1-11).

- Cây lưu ở `skill_trees` → `tree_versions` → `concept_nodes` / `prerequisite_edges` / `rubrics` (+ key_points,
  misconceptions, challenge_scenarios). Cạnh nối theo id nút trong CSDL; API trả theo `key` (ổn định giữa phiên bản).
- Mọi thao tác thêm cạnh kiểm chu trình trước khi ghi (`algorithms/dag.py`, BR-01); tạo chu trình ⇒ 409
  `CYCLE_DETECTED` kèm `details.path` (FR-SK-07, TC03).
- Chỉ phiên bản DRAFT / EDITING sửa được; phát hành (BR-05: DAG, có nút gốc, mọi rubric đã duyệt) ⇒ PUBLISHED,
  bản phát hành trước ⇒ ARCHIVED. Muốn sửa tiếp: tạo bản nháp mới từ bản đang phát hành (`create_version`).
- Quyền (Bảng 5.13): GV chỉ lớp mình (`class_sections.lecturer_id`); SV chỉ xem cây đã phát hành của lớp đã tham gia.
- Lớp mẫu `SEED_CLASS_ID` (C2-02): khi CSDL chưa có cây của lớp này (hoặc không kết nối được CSDL) thì đọc
  `seed/tree_ctdl_gt.json` như trước, để giao diện chạy được khi chưa nạp seed.
- C1-10 (Đăng) giao cây nháp của AI qua `create_version(class_id, user, tree, sanitize=True)` → trả kèm cạnh đã bỏ.
- Phát hành gọi `MasteryService.init_or_migrate` trong cùng giao dịch (khởi tạo / di chuyển trạng thái SV, BR-14,
  C2-10).
"""

import json
import logging
import re
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, UUID, uuid5

import networkx as nx
from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.algorithms.dag import build_graph, find_cycle, roots, sanitize, would_create_cycle
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import tree as orm
from app.models.enums import EdgeSource, Role, RubricStatus, TreeStatus
from app.models.schemas.session import DEFAULT_CRITERION_WEIGHTS
from app.models.schemas.tree import (
    ChallengeScenarioSchema,
    Edge,
    EdgeRef,
    KeyPointSchema,
    MisconceptionSchema,
    Node,
    NodePatch,
    Rubric,
    TreeDiff,
    TreeVersion,
)
from app.models.users import ClassSection, Enrollment

if TYPE_CHECKING:
    from app.api.deps import CurrentUser

log = logging.getLogger(__name__)

_NS = uuid5(NAMESPACE_URL, "https://whybi.ai/seed")
SEED_CLASS_ID = uuid5(_NS, "class/CTDL2026")
SEED_TREE_FILE = "tree_ctdl_gt.json"
EDITABLE = {TreeStatus.DRAFT, TreeStatus.EDITING}
_REQUIRED_NODE_FIELDS = {"title", "bloom_level"}


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


def _natural(s: str | None) -> list[Any]:
    """N2 < N10, KP2 < KP10."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s or "")]


def _cycle_error(path: list[str]) -> AppError:
    return AppError(409, "CYCLE_DETECTED", "Thêm cạnh này sẽ tạo chu trình: " + " → ".join(path), {"path": path})


class SkillTreeService:
    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    # ------------------------------------------------------------------ quyền, nạp bản ghi

    def _class(self, class_id: UUID) -> ClassSection:
        cls = self.db.get(ClassSection, class_id)
        if cls is None:
            raise AppError(404, "CLASS_NOT_FOUND", "Không tìm thấy lớp", {"classId": str(class_id)})
        return cls

    @staticmethod
    def _require_owner(cls: ClassSection, user: "CurrentUser") -> None:
        if user.role != Role.LECTURER or cls.lecturer_id != user.id:
            raise AppError(403, "NOT_CLASS_OWNER", "Chỉ GV phụ trách lớp được thao tác")

    def _require_member(self, cls: ClassSection, user: "CurrentUser") -> None:
        if user.role == Role.STUDENT:
            enrolled = self.db.scalar(
                select(Enrollment.id).where(Enrollment.class_id == cls.id, Enrollment.student_id == user.id)
            )
            if enrolled is None:
                raise AppError(403, "NOT_ENROLLED", "Bạn chưa tham gia lớp này")
        else:
            self._require_owner(cls, user)

    def _version(self, version_id: UUID, user: "CurrentUser", editable: bool = True) -> orm.TreeVersion:
        tree_id = self.db.scalar(select(orm.TreeVersion.tree_id).where(orm.TreeVersion.id == version_id))
        if tree_id is None:
            raise AppError(404, "VERSION_NOT_FOUND", "Không tìm thấy phiên bản cây")
        # One lock order for every edit/publish: tree before version. Refresh after waiting
        # so an already-loaded ORM instance cannot retain the old editable/published state.
        tree = self.db.scalar(
            select(orm.SkillTree)
            .where(orm.SkillTree.id == tree_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        v = self.db.scalar(
            select(orm.TreeVersion)
            .where(orm.TreeVersion.id == version_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        self._require_owner(self._class(tree.class_id), user)
        if editable and v.status not in EDITABLE:
            raise AppError(
                409,
                "VERSION_NOT_EDITABLE",
                "Phiên bản đã phát hành / lưu trữ – tạo bản nháp mới để sửa",
                {"status": v.status},
            )
        return v

    def _node(self, node_id: UUID, user: "CurrentUser") -> tuple[orm.ConceptNode, orm.TreeVersion]:
        n = self.db.get(orm.ConceptNode, node_id)
        if n is None:
            raise AppError(404, "NODE_NOT_FOUND", "Không tìm thấy nút")
        v = self._version(n.version_id, user)
        self.db.refresh(n)
        return n, v

    def _touch(self, v: orm.TreeVersion) -> None:
        if v.status == TreeStatus.DRAFT:
            v.status = TreeStatus.EDITING

    # ------------------------------------------------------------------ ORM → schema

    def _rubrics(self, nodes: list[orm.ConceptNode]) -> dict[UUID, Rubric]:
        ids = [n.id for n in nodes]
        if not ids:
            return {}
        by_node: dict[UUID, dict[str, list]] = {i: {"kp": [], "mc": [], "sc": []} for i in ids}
        for kp in self.db.scalars(select(orm.KeyPoint).where(orm.KeyPoint.node_id.in_(ids))):
            by_node[kp.node_id]["kp"].append(kp)
        for mc in self.db.scalars(select(orm.Misconception).where(orm.Misconception.node_id.in_(ids))):
            by_node[mc.node_id]["mc"].append(mc)
        for sc in self.db.scalars(select(orm.ChallengeScenario).where(orm.ChallengeScenario.node_id.in_(ids))):
            by_node[sc.node_id]["sc"].append(sc)
        min_ch = {n.id: n.min_challenges for n in nodes}
        out: dict[UUID, Rubric] = {}
        for r in self.db.scalars(select(orm.Rubric).where(orm.Rubric.node_id.in_(ids))):
            parts = by_node[r.node_id]
            kps = sorted(parts["kp"], key=lambda x: _natural(x.code))
            mcs = sorted(parts["mc"], key=lambda x: _natural(x.code))
            scs = sorted(parts["sc"], key=lambda x: _natural(x.code))
            out[r.node_id] = Rubric(
                key_points=[
                    KeyPointSchema(id=k.code or f"KP{i}", content=k.content, is_required=k.is_required)
                    for i, k in enumerate(kps, 1)
                ],
                optional_points=r.optional_points or [],
                misconceptions=[
                    MisconceptionSchema(
                        id=m.code or f"MC{i}",
                        content=m.content,
                        probe_question=m.probe_question,
                        is_critical=m.is_critical,
                    )
                    for i, m in enumerate(mcs, 1)
                ],
                scenarios=[
                    ChallengeScenarioSchema(
                        id=s.code or f"SC{i}",
                        scenario=s.scenario,
                        bloom_level=s.bloom_level,
                        expected_points=s.expected_points,
                    )
                    for i, s in enumerate(scs, 1)
                ],
                target_bloom=r.target_bloom,
                pass_threshold=r.pass_threshold,
                min_challenges=min_ch[r.node_id],
                min_passed_challenges=r.min_passed_challenges,
                source_pages=r.source_pages or [],
                approved=r.status == RubricStatus.APPROVED,
            )
        return out

    @staticmethod
    def _node_schema(n: orm.ConceptNode, rubric: Rubric | None = None) -> Node:
        return Node(
            id=n.id,
            key=n.key,
            code=n.code,
            title=n.title,
            description=n.description,
            chapter_ref=n.chapter_ref,
            bloom_level=n.bloom_level,
            position_x=n.position_x,
            position_y=n.position_y,
            rubric=rubric,
        )

    def _to_schema(self, v: orm.TreeVersion, class_id: UUID) -> TreeVersion:
        nodes = sorted(
            self.db.scalars(select(orm.ConceptNode).where(orm.ConceptNode.version_id == v.id)),
            key=lambda n: _natural(n.code or n.key),
        )
        key_of = {n.id: n.key for n in nodes}
        rubrics = self._rubrics(nodes)
        edges = self.db.scalars(select(orm.PrerequisiteEdge).where(orm.PrerequisiteEdge.version_id == v.id))
        return TreeVersion(
            id=v.id,
            class_id=class_id,
            version_no=v.version_no,
            status=v.status,
            change_note=v.change_note,
            published_at=v.published_at,
            nodes=[self._node_schema(n, rubrics.get(n.id)) for n in nodes],
            edges=sorted(
                (
                    Edge(
                        id=e.id,
                        from_key=key_of[e.from_node_id],
                        to_key=key_of[e.to_node_id],
                        source=e.source,
                        confidence=e.confidence,
                    )
                    for e in edges
                ),
                key=lambda e: (_natural(e.from_key), _natural(e.to_key)),
            ),
        )

    # ------------------------------------------------------------------ đọc

    def published_node_keys(self, class_id: UUID, node_ids: list[UUID] | None = None) -> dict[UUID, str]:
        """id nút → key của bản đang phát hành, theo thứ tự key – lời gọi nội bộ (MasteryService.columns C2-11).

        `node_ids` lọc nút; id không thuộc bản đang phát hành bị bỏ qua. Lớp chưa phát hành ⇒ {}."""
        self._class(class_id)
        published = select(orm.SkillTree.published_version_id).where(orm.SkillTree.class_id == class_id)
        q = select(orm.ConceptNode.id, orm.ConceptNode.key).where(
            orm.ConceptNode.version_id == published.scalar_subquery()
        )
        if node_ids is not None:
            q = q.where(orm.ConceptNode.id.in_(node_ids))
        return {nid: key for nid, key in self.db.execute(q.order_by(orm.ConceptNode.key))}

    def published_class_ids(self) -> list[UUID]:
        """Lớp đã phát hành cây – lời gọi nội bộ (đối soát heatmap C2-11), không kiểm quyền."""
        return list(
            self.db.scalars(select(orm.SkillTree.class_id).where(orm.SkillTree.published_version_id.is_not(None)))
        )

    def statuses_for(self, class_ids: list[UUID]) -> dict[UUID, str]:
        """Trạng thái cây theo lớp cho danh sách lớp (C2-08).
        Đã phát hành ⇒ PUBLISHED; chưa ⇒ trạng thái phiên bản mới nhất; chưa có cây ⇒ không có khóa."""
        rows = self.db.execute(
            select(
                orm.SkillTree.class_id,
                orm.SkillTree.published_version_id,
                orm.TreeVersion.status,
            )
            .join(orm.TreeVersion, orm.TreeVersion.tree_id == orm.SkillTree.id, isouter=True)
            .where(orm.SkillTree.class_id.in_(class_ids))
            .order_by(orm.SkillTree.class_id, orm.TreeVersion.version_no)
        ).all()
        out: dict[UUID, str] = {}
        for class_id, published, status in rows:
            if published is not None:
                out[class_id] = TreeStatus.PUBLISHED
            elif status is not None:
                out[class_id] = status  # bản sau ghi đè ⇒ còn lại phiên bản mới nhất
        return out

    def node_keys(self, node_ids: list[UUID]) -> dict[UUID, str]:
        """id nút → key (mọi phiên bản) – lời gọi nội bộ (MatchingService), không kiểm quyền."""
        if not node_ids:
            return {}
        rows = self.db.execute(select(orm.ConceptNode.id, orm.ConceptNode.key).where(orm.ConceptNode.id.in_(node_ids)))
        return {nid: key for nid, key in rows}

    def version_schema(self, version_id: UUID) -> TreeVersion:
        """Một phiên bản cây (kèm rubric) theo id – lời gọi nội bộ (MasteryService), không kiểm quyền."""
        v = self.db.get(orm.TreeVersion, version_id)
        if v is None:
            raise AppError(404, "VERSION_NOT_FOUND", "Không tìm thấy phiên bản cây")
        tree = self.db.get(orm.SkillTree, v.tree_id)
        return self._to_schema(v, tree.class_id)

    def _seed_tree(self) -> TreeVersion:
        return load_seed_tree().model_copy(deep=True)

    def get_class_tree(self, class_id: UUID, *, user: "CurrentUser | None", draft: bool = False) -> TreeVersion:
        """Cây đang phát hành của lớp; GV phụ trách gọi `draft=True` thì lấy phiên bản mới nhất (FR-SK-04).
        `user=None` chỉ dành cho lời gọi nội bộ (worker) – bỏ kiểm quyền; router luôn truyền người dùng."""
        if self.db is None:
            if class_id == SEED_CLASS_ID:
                return self._seed_tree()
            raise AppError(404, "CLASS_NOT_FOUND", "Không tìm thấy lớp", {"classId": str(class_id)})
        try:
            tree = self.db.scalar(select(orm.SkillTree).where(orm.SkillTree.class_id == class_id))
        except OperationalError:
            if class_id != SEED_CLASS_ID:
                raise
            log.warning("không kết nối được CSDL – trả cây mẫu từ seed/")
            return self._seed_tree()
        if tree is None and class_id == SEED_CLASS_ID:
            return self._seed_tree()
        cls = self._class(class_id)
        if user is not None:
            self._require_member(cls, user)
        if tree is None:
            raise AppError(404, "TREE_NOT_FOUND", "Lớp chưa có cây kỹ năng")
        if draft and user is not None and user.role == Role.LECTURER:
            v = self.db.scalar(
                select(orm.TreeVersion)
                .where(orm.TreeVersion.tree_id == tree.id)
                .order_by(orm.TreeVersion.version_no.desc())
                .limit(1)
            )
        else:
            v = self.db.get(orm.TreeVersion, tree.published_version_id) if tree.published_version_id else None
            if v is None:
                raise AppError(404, "TREE_NOT_PUBLISHED", "Lớp chưa phát hành cây kỹ năng")
        return self._to_schema(v, class_id)

    # ------------------------------------------------------------------ tạo phiên bản

    def create_version(
        self,
        class_id: UUID,
        user: "CurrentUser",
        body: TreeVersion | None = None,
        sanitize_graph: bool = False,
        removed_edges: list[tuple[str, str]] | None = None,
    ) -> TreeVersion:
        """Tạo phiên bản DRAFT mới.

        - `body` có: nhập cây (GV dán / seed / AI của C1-10). `sanitize_graph=True` chạy hậu xử lý 6.1.4 (phá chu
          trình, rút gọn bắc cầu); cạnh bị bỏ được thêm vào `removed_edges` nếu truyền list. Không sanitize mà có
          chu trình ⇒ 409 CYCLE_DETECTED.
        - `body` không có: sao bản đang phát hành (hoặc mới nhất) để sửa tiếp.
        """
        cls = self._class(class_id)
        self._require_owner(cls, user)
        self.db.refresh(cls, with_for_update=True)
        tree = self.db.scalar(
            select(orm.SkillTree)
            .where(orm.SkillTree.class_id == class_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if body is not None:
            # Cây nhập vào (AI / dán / seed) luôn chờ GV duyệt rubric (FR-SK-08) – không tin cờ `approved` của body
            body = body.model_copy(deep=True)
            for n in body.nodes:
                if n.rubric is not None:
                    n.rubric.approved = False
        else:
            if tree is None:
                raise AppError(404, "TREE_NOT_FOUND", "Lớp chưa có cây để sao")
            src_id = tree.published_version_id or self.db.scalar(
                select(orm.TreeVersion.id)
                .where(orm.TreeVersion.tree_id == tree.id)
                .order_by(orm.TreeVersion.version_no.desc())
                .limit(1)
            )
            body = self._to_schema(self.db.get(orm.TreeVersion, src_id), class_id)
            body.change_note = f"Sao từ phiên bản {body.version_no}"

        g = build_graph(body)
        edges = body.edges
        if sanitize_graph:
            dag, _layers, removed = sanitize(g)
            edges = [e for e in body.edges if dag.has_edge(e.from_key, e.to_key)]
            if removed_edges is not None:
                removed_edges.extend(removed)
        else:
            cycle = find_cycle(g)
            if cycle:
                raise _cycle_error([*cycle, cycle[0]])

        if tree is None:
            tree = orm.SkillTree(class_id=class_id, title=cls.name)
            self.db.add(tree)
            self.db.flush()
        last = self.db.scalar(select(func.max(orm.TreeVersion.version_no)).where(orm.TreeVersion.tree_id == tree.id))
        v = orm.TreeVersion(
            tree_id=tree.id,
            version_no=(last or 0) + 1,
            status=TreeStatus.DRAFT,
            change_note=body.change_note,
            created_by=user.id,
        )
        self.db.add(v)
        self.db.flush()
        id_of: dict[str, UUID] = {}
        for n in body.nodes:
            row = self._new_node(v.id, n)
            id_of[n.key] = row.id
            if n.rubric is not None:
                self._write_rubric(row, n.rubric, user)
        for e in edges:
            self.db.add(
                orm.PrerequisiteEdge(
                    version_id=v.id,
                    from_node_id=id_of[e.from_key],
                    to_node_id=id_of[e.to_key],
                    source=e.source,
                    confidence=e.confidence,
                )
            )
        self.db.commit()
        return self._to_schema(v, class_id)

    # ------------------------------------------------------------------ lịch sử, so sánh, khôi phục (C2-16)

    def list_versions(self, class_id: UUID, user: "CurrentUser") -> list[TreeVersion]:
        """Mọi phiên bản của lớp, mới nhất trước (FR-SK-10). Lớp chưa có cây ⇒ danh sách rỗng."""
        self._require_owner(self._class(class_id), user)
        tree = self.db.scalar(select(orm.SkillTree).where(orm.SkillTree.class_id == class_id))
        if tree is None:
            return []
        rows = self.db.scalars(
            select(orm.TreeVersion)
            .where(orm.TreeVersion.tree_id == tree.id)
            .order_by(orm.TreeVersion.version_no.desc())
        )
        return [self._to_schema(v, class_id) for v in rows]

    def _owned_schema(self, version_id: UUID, user: "CurrentUser") -> TreeVersion:
        v = self.db.get(orm.TreeVersion, version_id)
        if v is None:
            raise AppError(404, "VERSION_NOT_FOUND", "Không tìm thấy phiên bản cây")
        class_id = self.db.get(orm.SkillTree, v.tree_id).class_id
        self._require_owner(self._class(class_id), user)
        return self._to_schema(v, class_id)

    def restore_version(self, version_id: UUID, user: "CurrentUser") -> TreeVersion:
        """Sao phiên bản cũ thành bản nháp mới (FR-SK-10). Bản cũ giữ nguyên; rubric phải duyệt lại như mọi cây nhập."""
        old = self._owned_schema(version_id, user)
        old.change_note = f"Khôi phục từ phiên bản {old.version_no}"
        return self.create_version(old.class_id, user, old)

    def compare_versions(self, a_id: UUID, b_id: UUID, user: "CurrentUser") -> TreeDiff:
        """Khác biệt từ phiên bản a sang b, so theo key nút (bỏ qua id vì mỗi phiên bản có id riêng)."""
        a, b = self._owned_schema(a_id, user), self._owned_schema(b_id, user)
        if a.class_id != b.class_id:
            raise AppError(422, "VERSIONS_DIFFERENT_CLASS", "Hai phiên bản thuộc hai lớp khác nhau")

        def body(n: Node) -> dict:
            return n.model_dump(mode="json", exclude={"id"})

        na, nb = {n.key: n for n in a.nodes}, {n.key: n for n in b.nodes}
        ea = {(e.from_key, e.to_key) for e in a.edges}
        eb = {(e.from_key, e.to_key) for e in b.edges}

        def refs(pairs: set[tuple[str, str]]) -> list[EdgeRef]:
            return [
                EdgeRef(from_key=f, to_key=t) for f, t in sorted(pairs, key=lambda p: (_natural(p[0]), _natural(p[1])))
            ]

        return TreeDiff(
            from_version_no=a.version_no,
            to_version_no=b.version_no,
            nodes_added=sorted(nb.keys() - na.keys(), key=_natural),
            nodes_removed=sorted(na.keys() - nb.keys(), key=_natural),
            nodes_changed=sorted((k for k in na.keys() & nb.keys() if body(na[k]) != body(nb[k])), key=_natural),
            edges_added=refs(eb - ea),
            edges_removed=refs(ea - eb),
        )

    def _new_node(self, version_id: UUID, n: Node) -> orm.ConceptNode:
        row = orm.ConceptNode(
            version_id=version_id,
            key=n.key,
            code=n.code,
            title=n.title,
            description=n.description,
            chapter_ref=n.chapter_ref,
            bloom_level=n.bloom_level,
            position_x=n.position_x,
            position_y=n.position_y,
            min_challenges=n.rubric.min_challenges if n.rubric else 3,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _write_rubric(self, node: orm.ConceptNode, r: Rubric, user: "CurrentUser") -> None:
        for model in (orm.KeyPoint, orm.Misconception, orm.ChallengeScenario):
            self.db.execute(delete(model).where(model.node_id == node.id))
        approved = r.approved
        row = self.db.scalar(select(orm.Rubric).where(orm.Rubric.node_id == node.id))
        if row is None:
            row = orm.Rubric(node_id=node.id)
            self.db.add(row)
            self.db.flush()
            for code, weight in DEFAULT_CRITERION_WEIGHTS.items():
                self.db.add(
                    orm.RubricCriterion(
                        rubric_id=row.id, code=code.value, name=code.value, weight=weight, max_score=100
                    )
                )
        # Preserve the rubric identity and its criteria, including lecturer-tuned weights.
        for name, value in dict(
            pass_threshold=r.pass_threshold,
            status=RubricStatus.APPROVED if approved else RubricStatus.DRAFT,
            approved_by=user.id if approved else None,
            approved_at=datetime.now(UTC) if approved else None,
            target_bloom=r.target_bloom,
            min_passed_challenges=r.min_passed_challenges,
            optional_points=list(r.optional_points),
            source_pages=list(r.source_pages),
        ).items():
            setattr(row, name, value)
        for k in r.key_points:
            self.db.add(orm.KeyPoint(node_id=node.id, code=k.id, content=k.content, is_required=k.is_required))
        for m in r.misconceptions:
            self.db.add(
                orm.Misconception(
                    node_id=node.id,
                    code=m.id,
                    content=m.content,
                    probe_question=m.probe_question,
                    is_critical=m.is_critical,
                )
            )
        for s in r.scenarios:
            self.db.add(
                orm.ChallengeScenario(
                    node_id=node.id,
                    code=s.id,
                    scenario=s.scenario,
                    bloom_level=s.bloom_level,
                    expected_points=s.expected_points,
                )
            )
        node.min_challenges = r.min_challenges
        self.db.flush()

    # ------------------------------------------------------------------ sửa cây (FR-SK-06, 07, 08)

    def add_node(self, version_id: UUID, body: Node, user: "CurrentUser") -> Node:
        v = self._version(version_id, user)
        exists = self.db.scalar(
            select(orm.ConceptNode.id).where(orm.ConceptNode.version_id == v.id, orm.ConceptNode.key == body.key)
        )
        if exists:
            raise AppError(409, "NODE_KEY_EXISTS", f"Đã có nút với key {body.key}", {"key": body.key})
        row = self._new_node(v.id, body)
        if body.rubric is not None:
            self._write_rubric(row, body.rubric, user)
        self._touch(v)
        self.db.commit()
        return self._node_schema(row, self._rubrics([row]).get(row.id))

    def update_node(self, node_id: UUID, patch: NodePatch, user: "CurrentUser") -> Node:
        n, v = self._node(node_id, user)
        for field, value in patch.model_dump(exclude_unset=True).items():
            if value is None and field in _REQUIRED_NODE_FIELDS:
                raise AppError(422, "VALIDATION_ERROR", f"Trường {field} không được rỗng", {"field": field})
            setattr(n, field, value)
        self._touch(v)
        self.db.commit()
        return self._node_schema(n, self._rubrics([n]).get(n.id))

    def add_edge(self, version_id: UUID, body: Edge, user: "CurrentUser") -> Edge:
        """Kiểm chu trình trước khi ghi (BR-01). Cạnh GV nối luôn source=LECTURER, confidence=1."""
        v = self._version(version_id, user)
        nodes = {
            n.key: n.id for n in self.db.scalars(select(orm.ConceptNode).where(orm.ConceptNode.version_id == v.id))
        }
        for k in (body.from_key, body.to_key):
            if k not in nodes:
                raise AppError(404, "NODE_NOT_FOUND", f"Không có nút {k} trong phiên bản này", {"key": k})
        key_of = {i: k for k, i in nodes.items()}
        rows = list(self.db.scalars(select(orm.PrerequisiteEdge).where(orm.PrerequisiteEdge.version_id == v.id)))
        pairs = {(key_of[e.from_node_id], key_of[e.to_node_id]) for e in rows}
        if (body.from_key, body.to_key) in pairs:
            raise AppError(409, "EDGE_EXISTS", "Cạnh này đã có")
        g = nx.DiGraph(list(pairs))
        g.add_nodes_from(nodes)
        path = would_create_cycle(g, body.from_key, body.to_key)
        if path:
            raise _cycle_error(path)
        e = orm.PrerequisiteEdge(
            version_id=v.id,
            from_node_id=nodes[body.from_key],
            to_node_id=nodes[body.to_key],
            source=EdgeSource.LECTURER,
            confidence=1.0,
        )
        self.db.add(e)
        self._touch(v)
        self.db.commit()
        return Edge(id=e.id, from_key=body.from_key, to_key=body.to_key, source=e.source, confidence=e.confidence)

    def delete_edge(self, edge_id: UUID, user: "CurrentUser") -> None:
        e = self.db.get(orm.PrerequisiteEdge, edge_id)
        if e is None:
            raise AppError(404, "EDGE_NOT_FOUND", "Không tìm thấy cạnh")
        v = self._version(e.version_id, user)
        self.db.delete(e)
        self._touch(v)
        self.db.commit()

    def node_for_edit(self, node_id: UUID, user: "CurrentUser") -> tuple[UUID, Node]:
        """(class_id, Node) của nút trong bản nháp mà GV chủ lớp được sửa. Kiểm quyền / trạng thái nhưng KHÔNG khóa
        dòng: bên gọi (sinh lại rubric, C1-11) còn chờ LLM hàng giây."""
        n = self.db.get(orm.ConceptNode, node_id)
        if n is None:
            raise AppError(404, "NODE_NOT_FOUND", "Không tìm thấy nút")
        v = self.db.get(orm.TreeVersion, n.version_id)
        tree = self.db.get(orm.SkillTree, v.tree_id)
        self._require_owner(self._class(tree.class_id), user)
        if v.status not in EDITABLE:
            raise AppError(
                409,
                "VERSION_NOT_EDITABLE",
                "Phiên bản đã phát hành / lưu trữ – tạo bản nháp mới để sửa",
                {"status": v.status},
            )
        return self.get_node_for_session(node_id)

    def put_rubric(self, node_id: UUID, body: Rubric, user: "CurrentUser") -> Rubric:
        """Sửa / duyệt rubric (FR-SK-08). `approved=true` ghi người duyệt và thời điểm."""
        n, v = self._node(node_id, user)
        self._write_rubric(n, body, user)
        self._touch(v)
        self.db.commit()
        return self._rubrics([n])[n.id]

    # ------------------------------------------------------------------ phát hành (FR-SK-09, BR-05)

    def publish(self, version_id: UUID, user: "CurrentUser") -> TreeVersion:
        v = self._version(version_id, user)
        tree = self.db.get(orm.SkillTree, v.tree_id)
        schema = self._to_schema(v, tree.class_id)
        errors: list[dict[str, Any]] = []
        if not schema.nodes:
            errors.append({"code": "EMPTY_TREE", "message": "Cây chưa có nút"})
        g = build_graph(schema)
        cycle = find_cycle(g)
        if cycle:
            errors.append({"code": "CYCLE_DETECTED", "message": "Cây có chu trình", "path": [*cycle, cycle[0]]})
        elif schema.nodes and not roots(g):
            errors.append({"code": "NO_ROOT", "message": "Cây không có nút gốc"})
        for n in schema.nodes:
            if n.rubric is None or not n.rubric.approved:
                errors.append(
                    {"code": "RUBRIC_NOT_APPROVED", "nodeKey": n.key, "message": f"Rubric {n.title} chưa duyệt"}
                )
        if errors:
            raise AppError(422, "PUBLISH_CHECK_FAILED", "Chưa đủ điều kiện phát hành (BR-05)", {"errors": errors})

        if tree.published_version_id and tree.published_version_id != v.id:
            old = self.db.get(orm.TreeVersion, tree.published_version_id)
            old.status = TreeStatus.ARCHIVED
        v.status = TreeStatus.PUBLISHED
        v.published_at = datetime.now(UTC)
        tree.published_version_id = v.id
        self.db.flush()
        # BR-14: khởi tạo / di chuyển ma trận thành thạo – commit chung giao dịch phát hành rồi mới phát mastery.changed
        from app.services.mastery import MasteryService

        MasteryService(self.db).init_or_migrate(tree.class_id, v.id)
        return self._to_schema(v, tree.class_id)

    def build_draft_tree(self, document_id):
        raise NotImplementedError("C1-10")
