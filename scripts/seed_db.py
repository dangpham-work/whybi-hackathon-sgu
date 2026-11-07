"""Nạp dữ liệu mẫu seed/ vào CSDL (KT-02): 1 GV, 1 QTV, 30 SV, lớp CTDL&GT – Nhóm 02, cây mẫu 11 nút.

    cd backend && uv run python ../scripts/seed_db.py           # nạp vào DATABASE_URL (cần đã `alembic upgrade head`)
    cd backend && uv run python ../scripts/seed_db.py --check   # chỉ đọc + kiểm seed/, không đụng CSDL

Chạy lại an toàn: bỏ qua bản ghi đã có (theo email, mã môn, mã tham gia lớp, cây của lớp).
Cây đọc đúng schema hợp đồng `app/models/schemas/tree.py` (camelCase).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Annotated
from uuid import NAMESPACE_URL, uuid5

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "seed"
sys.path.insert(0, str(ROOT / "backend"))  # để `import app...` khi chạy từ bất kỳ đâu

from app.models.schemas.tree import TreeVersion

DEFAULT_PASSWORD = "Whybi@2026"  # chỉ dev/demo – xem seed/users.json
TREE_TITLE = "Cây kỹ năng CTDL&GT"
EXPECTED_STUDENTS = 30
NODE_RANGE = (11, 11)  # Điều phối duyệt giữ cây C2-02 đã merge (gồm AVL).
SEED_NAMESPACE = uuid5(NAMESPACE_URL, "https://whybi.ai/seed")

# Bảng 6.4 đề cương: 5 tiêu chí, trọng số mặc định (Σ = 1)
CRITERIA = [
    ("CORRECTNESS", "Đúng đắn", 0.25),
    ("COVERAGE", "Bao phủ ý chính", 0.25),
    ("ESSENCE", "Bản chất – vì sao", 0.20),
    ("ROBUSTNESS", "Đứng vững trước phản biện", 0.20),
    ("CLARITY", "Diễn đạt mạch lạc", 0.10),
]


# ---------- Mô hình đọc seed/ (snake_case như file JSON) ----------

# Không dùng EmailStr: email-validator chặn đuôi `.test` (tên miền dành riêng) mà tài khoản demo dùng.
Email = Annotated[
    str, Field(pattern=r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$", max_length=150)
]


class _Seed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SeedLecturer(_Seed):
    email: Email
    full_name: str
    faculty: str | None = None
    academic_title: str | None = None


class SeedAdmin(_Seed):
    email: Email
    full_name: str


class SeedStudent(_Seed):
    email: Email
    full_name: str
    student_code: str = Field(max_length=20)
    cohort: str | None = None


class SeedUsers(_Seed):
    password_note: str | None = None
    lecturers: list[SeedLecturer]
    admins: list[SeedAdmin]
    students: list[SeedStudent]

    def all_accounts(self) -> list[SeedLecturer | SeedAdmin | SeedStudent]:
        return [*self.lecturers, *self.admins, *self.students]


class SeedCourse(_Seed):
    code: str = Field(max_length=20)
    name: str
    credits: int | None = None


class SeedClassSection(_Seed):
    name: str
    semester: str = Field(max_length=20)
    join_code: str = Field(min_length=8, max_length=8)
    lecturer_email: Email
    pass_threshold: int = Field(70, ge=0, le=100)
    color_thresholds: dict[str, float]
    min_sample: int = 5


class SeedClass(_Seed):
    course: SeedCourse
    class_: SeedClassSection = Field(alias="class")
    enroll_all_students: bool = True
    peer_opt_in_all: bool = False


class SeedBundle(BaseModel):
    users: SeedUsers
    klass: SeedClass
    tree: TreeVersion


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_seed(seed_dir: Path = SEED) -> SeedBundle:
    """Đọc và parse seed/*.json; sai schema → pydantic.ValidationError."""
    tree_raw = {
        k: v
        for k, v in _read(seed_dir / "tree_ctdl_gt.json").items()
        if not k.startswith("_")
    }
    return SeedBundle(
        users=SeedUsers.model_validate(_read(seed_dir / "users.json")),
        klass=SeedClass.model_validate(_read(seed_dir / "class.json")),
        tree=TreeVersion.model_validate(tree_raw),
    )


def check_seed(bundle: SeedBundle) -> list[str]:
    """Kiểm ràng buộc nghiệp vụ của dữ liệu mẫu. Trả danh sách lỗi (rỗng = sạch)."""
    errors: list[str] = []
    users, tree = bundle.users, bundle.tree

    emails = [u.email.lower() for u in users.all_accounts()]
    dup = sorted({e for e in emails if emails.count(e) > 1})
    if dup:
        errors.append(f"email trùng: {dup}")
    codes = [s.student_code for s in users.students]
    if len(codes) != len(set(codes)):
        errors.append("MSSV trùng")
    if len(users.students) != EXPECTED_STUDENTS:
        errors.append(f"cần {EXPECTED_STUDENTS} SV, có {len(users.students)}")
    if len(users.lecturers) != 1 or len(users.admins) != 1:
        errors.append("cần đúng 1 GV và 1 QTV")
    if bundle.klass.class_.lecturer_email not in {gv.email for gv in users.lecturers}:
        errors.append("lecturer_email của lớp không có trong danh sách GV")

    keys = [n.key for n in tree.nodes]
    if len(keys) != len(set(keys)):
        errors.append("key nút trùng")
    if not NODE_RANGE[0] <= len(keys) <= NODE_RANGE[1]:
        errors.append(f"cây cần {NODE_RANGE[0]}–{NODE_RANGE[1]} nút, có {len(keys)}")
    missing = {k for e in tree.edges for k in (e.from_key, e.to_key)} - set(keys)
    if missing:
        errors.append(f"cạnh trỏ tới key không tồn tại: {sorted(missing)}")
    # TODO(C2-09): khi algorithms/dag.py xong, dùng chung hàm kiểm chu trình ở đó (một chỗ duy nhất)
    g = nx.DiGraph()
    g.add_nodes_from(keys)
    g.add_edges_from((e.from_key, e.to_key) for e in tree.edges)
    if not nx.is_directed_acyclic_graph(g):
        errors.append(f"cây có chu trình: {nx.find_cycle(g)}")

    n5 = next((n for n in tree.nodes if n.code == "N5"), None)
    if n5 is None or n5.title != "Con trỏ":
        errors.append('thiếu nút N5 "Con trỏ" (kịch bản demo)')
    elif n5.rubric is None or not n5.rubric.approved:
        errors.append("N5 Con trỏ cần rubric đã duyệt")
    return errors


# ---------- Ghi CSDL ----------


def _hash_password(plain: str) -> str:
    """Dùng app.core.security khi C2-07 xong; trước đó băm Argon2id trực tiếp (cùng thuật toán NFR-07)."""
    from app.core.security import hash_password

    try:
        return hash_password(plain)
    except NotImplementedError:
        from argon2 import PasswordHasher

        return PasswordHasher().hash(plain)


def write_db(db, bundle: SeedBundle) -> dict[str, int]:
    """Upsert (bỏ qua nếu đã có) toàn bộ dữ liệu mẫu trong một transaction. Trả số bản ghi mới tạo."""
    from app.models.tree import (
        ChallengeScenario,
        ConceptNode,
        KeyPoint,
        Misconception,
        PrerequisiteEdge,
        Rubric,
        RubricCriterion,
        SkillTree,
    )
    from app.models.tree import TreeVersion as TreeVersionRow
    from app.models.users import (
        ClassSection,
        Course,
        Enrollment,
        Lecturer,
        Student,
        User,
    )
    from sqlalchemy import select

    created = {"users": 0, "classes": 0, "enrollments": 0, "trees": 0}
    pw_hash = _hash_password(DEFAULT_PASSWORD)

    def get_or_create_user(email: str, full_name: str, role: str) -> tuple[User, bool]:
        user = db.scalar(select(User).where(User.email == email))
        if user:
            return user, False
        user = User(email=email, full_name=full_name, role=role, password_hash=pw_hash)
        db.add(user)
        db.flush()
        created["users"] += 1
        return user, True

    users = bundle.users
    lecturer_ids: dict[str, object] = {}
    for gv in users.lecturers:
        user, new = get_or_create_user(gv.email, gv.full_name, "LECTURER")
        if new:
            db.add(
                Lecturer(
                    user_id=user.id,
                    faculty=gv.faculty,
                    academic_title=gv.academic_title,
                )
            )
        lecturer_ids[gv.email] = user.id
    for qtv in users.admins:
        get_or_create_user(qtv.email, qtv.full_name, "ADMIN")
    student_ids = []
    for sv in users.students:
        user, new = get_or_create_user(sv.email, sv.full_name, "STUDENT")
        if new:
            db.add(
                Student(user_id=user.id, student_code=sv.student_code, cohort=sv.cohort)
            )
        student_ids.append(user.id)
    db.flush()

    c, k = bundle.klass.course, bundle.klass.class_
    class_id = uuid5(SEED_NAMESPACE, f"class/{k.join_code}")
    course = db.scalar(select(Course).where(Course.code == c.code))
    if course is None:
        course = Course(code=c.code, name=c.name, credits=c.credits)
        db.add(course)
        db.flush()
    section = db.scalar(
        select(ClassSection).where(ClassSection.join_code == k.join_code)
    )
    if section is None:
        section = ClassSection(
            id=class_id,
            course_id=course.id,
            lecturer_id=lecturer_ids[k.lecturer_email],
            name=k.name,
            semester=k.semester,
            join_code=k.join_code,
            pass_threshold=k.pass_threshold,
            color_thresholds=k.color_thresholds,
            min_sample=k.min_sample,
        )
        db.add(section)
        db.flush()
        created["classes"] += 1
    elif section.id != class_id:
        raise ValueError(
            "Lớp seed cũ có UUID khác hợp đồng API; cần xử lý dữ liệu cũ trước khi nạp lại"
        )

    if bundle.klass.enroll_all_students:
        enrolled = set(
            db.scalars(
                select(Enrollment.student_id).where(Enrollment.class_id == section.id)
            )
        )
        for sid in student_ids:
            if sid not in enrolled:
                db.add(
                    Enrollment(
                        class_id=section.id,
                        student_id=sid,
                        peer_opt_in=bundle.klass.peer_opt_in_all,
                    )
                )
                created["enrollments"] += 1

    if db.scalar(select(SkillTree).where(SkillTree.class_id == section.id)) is None:
        t = bundle.tree
        tree_row = SkillTree(class_id=section.id, title=TREE_TITLE)
        db.add(tree_row)
        db.flush()
        version = TreeVersionRow(
            id=uuid5(SEED_NAMESPACE, f"class/{k.join_code}/version/{t.version_no}"),
            tree_id=tree_row.id,
            version_no=t.version_no,
            status=t.status.value,
            change_note=t.change_note or "Dữ liệu mẫu KT-02",
            created_by=lecturer_ids[k.lecturer_email],
        )
        db.add(version)
        db.flush()
        node_ids = {}
        for n in t.nodes:
            row = ConceptNode(
                id=uuid5(SEED_NAMESPACE, f"version/{t.version_no}/node/{n.key}"),
                version_id=version.id,
                key=n.key,
                code=n.code,
                title=n.title,
                description=n.description,
                chapter_ref=n.chapter_ref,
                bloom_level=n.bloom_level.value,
                position_x=n.position_x,
                position_y=n.position_y,
                min_challenges=n.rubric.min_challenges if n.rubric else 3,
            )
            db.add(row)
            db.flush()
            node_ids[n.key] = row.id
            if n.rubric:
                r = n.rubric
                rubric = Rubric(
                    node_id=row.id,
                    pass_threshold=r.pass_threshold,
                    status="APPROVED" if r.approved else "DRAFT",
                    approved_by=lecturer_ids[k.lecturer_email] if r.approved else None,
                    target_bloom=r.target_bloom.value,
                    min_passed_challenges=r.min_passed_challenges,
                    optional_points=list(r.optional_points),
                    source_pages=list(r.source_pages),
                )
                db.add(rubric)
                db.flush()
                for code, name, weight in CRITERIA:
                    db.add(
                        RubricCriterion(
                            rubric_id=rubric.id,
                            code=code,
                            name=name,
                            weight=weight,
                            max_score=100,
                        )
                    )
                for kp in r.key_points:
                    db.add(
                        KeyPoint(
                            node_id=row.id,
                            code=kp.id,
                            content=kp.content,
                            is_required=kp.is_required,
                        )
                    )
                for mc in r.misconceptions:
                    db.add(
                        Misconception(
                            node_id=row.id,
                            code=mc.id,
                            content=mc.content,
                            probe_question=mc.probe_question,
                            is_critical=mc.is_critical,
                        )
                    )
                for sc in r.scenarios:
                    db.add(
                        ChallengeScenario(
                            node_id=row.id,
                            code=sc.id,
                            scenario=sc.scenario,
                            bloom_level=sc.bloom_level.value,
                            expected_points=sc.expected_points,
                        )
                    )
        for e in t.edges:
            db.add(
                PrerequisiteEdge(
                    id=uuid5(
                        SEED_NAMESPACE,
                        f"version/{t.version_no}/edge/{e.from_key}->{e.to_key}",
                    ),
                    version_id=version.id,
                    from_node_id=node_ids[e.from_key],
                    to_node_id=node_ids[e.to_key],
                    source=e.source.value,
                    confidence=e.confidence,
                )
            )
        created["trees"] += 1
        if t.status.value == "PUBLISHED":
            tree_row.published_version_id = version.id

    db.commit()
    return created


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # console Windows
    parser = argparse.ArgumentParser(description="Nạp dữ liệu mẫu seed/ (KT-02)")
    parser.add_argument(
        "--check", action="store_true", help="chỉ đọc và kiểm seed/, không ghi CSDL"
    )
    args = parser.parse_args(argv)

    bundle = load_seed()
    errors = check_seed(bundle)
    u, t = bundle.users, bundle.tree
    print(
        f"{len(u.lecturers)} GV, {len(u.admins)} QTV, {len(u.students)} SV;"
        f" lớp {bundle.klass.class_.join_code}; cây {len(t.nodes)} nút / {len(t.edges)} cạnh"
    )
    if errors:
        for e in errors:
            print(f"LỖI: {e}", file=sys.stderr)
        return 1
    if args.check:
        print("seed/ hợp lệ (chế độ --check, không ghi CSDL)")
        return 0

    from app.db.session import SessionLocal

    with SessionLocal() as db:
        created = write_db(db, bundle)
    print(f"Đã nạp: {created} (0 = đã có từ trước)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
