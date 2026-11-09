"""Nạp dữ liệu demo đa lớp vào CSDL: 2 GV, 1 QTV, 90 SV dùng chung, 5 lớp nhiều môn (scripts/seed_data/).

    cd backend && uv run python ../scripts/seed_db.py           # nạp vào DATABASE_URL (cần đã `alembic upgrade head`)
    cd backend && uv run python ../scripts/seed_db.py --check   # chỉ kiểm dữ liệu mẫu, không đụng CSDL

Chạy lại an toàn: bỏ qua bản ghi đã có (theo email, mã môn, mã tham gia lớp, cây của lớp).
Sau khi ghi user/lớp/cây, mỗi lớp được "dựng lại tiến độ" qua scripts/seed_data/sessions.py (ghi thẳng qua
MasteryService, không gọi LLM) để có ngay dữ liệu demo: dồn lỗi vào 1 nút (MX3 cảnh báo), vài SV còn nguyên
để demo phiên thật (MX2), một nhóm SV bật tham gia ghép cặp (MX4).
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Annotated
from uuid import NAMESPACE_URL, UUID, uuid5

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent.parent
SEED = Path(os.getenv("SEED_DIR", str(ROOT / "seed")))
if not SEED.exists() and (ROOT / "seed").exists():
    SEED = ROOT / "seed"
sys.path.insert(0, str(ROOT / "backend"))  # để `import app...` khi chạy từ repo root
sys.path.insert(0, str(ROOT))  # để `import scripts.seed_data...` khi chạy từ repo root hoặc trong container
sys.path.insert(0, str(Path(__file__).resolve().parent))  # fallback

from app.models.schemas.tree import TreeVersion  # noqa: E402
from scripts.seed_data import classes as seed_classes  # noqa: E402
from scripts.seed_data import sessions as seed_sessions  # noqa: E402
from scripts.seed_data import trees as seed_trees  # noqa: E402
from scripts.seed_data import users as seed_users  # noqa: E402

DEFAULT_PASSWORD = "Whybi@2026"  # chỉ dev/demo
TREE_TITLE = "Cây kỹ năng"
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
Email = Annotated[str, Field(pattern=r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$", max_length=150)]


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
    """Tương thích ngược (KT-02/KT-15): đọc seed/*.json ra đúng lớp CTDL2026 gốc, như trước khi có đa lớp."""
    tree_raw = {k: v for k, v in _read(seed_dir / "tree_ctdl_gt.json").items() if not k.startswith("_")}
    return SeedBundle(
        users=SeedUsers.model_validate(_read(seed_dir / "users.json")),
        klass=SeedClass.model_validate(_read(seed_dir / "class.json")),
        tree=TreeVersion.model_validate(tree_raw),
    )


def check_seed(bundle: SeedBundle) -> list[str]:
    """Tương thích ngược: kiểm 1 bundle đơn lẻ (như check_all() nhưng cho gọi trực tiếp với 1 bundle)."""
    errors: list[str] = []
    users, tree = bundle.users, bundle.tree
    emails = [u.email.lower() for u in users.all_accounts()]
    dup = sorted({e for e in emails if emails.count(e) > 1})
    if dup:
        errors.append(f"email trùng: {dup}")
    codes = [s.student_code for s in users.students]
    if len(codes) != len(set(codes)):
        errors.append("MSSV trùng")
    if bundle.klass.class_.lecturer_email not in {gv.email for gv in users.lecturers}:
        errors.append("lecturer_email của lớp không có trong danh sách GV")
    keys = [n.key for n in tree.nodes]
    if len(keys) != len(set(keys)):
        errors.append("key nút trùng")
    missing = {k for e in tree.edges for k in (e.from_key, e.to_key)} - set(keys)
    if missing:
        errors.append(f"cạnh trỏ tới key không tồn tại: {sorted(missing)}")
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


def seed_of(join_code: str) -> int:
    """Seed tất định cho random.Random (hash() của str không ổn định giữa các lần chạy – PYTHONHASHSEED)."""
    return sum(ord(c) for c in join_code)


def build_tree(spec: "seed_classes.ClassSpec") -> TreeVersion:
    base = seed_trees.fixture_tree() if spec.base == "ctdl" else None
    return seed_trees.build(spec.tree_spec, base=base)


def build_bundle(spec: "seed_classes.ClassSpec") -> SeedBundle:
    """Lớp dùng toàn bộ GV/QTV (idempotent, bỏ qua trùng) nhưng chỉ phần SV trong student_range."""
    start, end = spec.student_range
    return SeedBundle(
        users=SeedUsers(
            lecturers=[
                SeedLecturer(
                    email=gv.email, full_name=gv.full_name, faculty=gv.faculty, academic_title=gv.academic_title
                )
                for gv in seed_users.LECTURERS.values()
            ],
            admins=[SeedAdmin(email=seed_users.ADMIN.email, full_name=seed_users.ADMIN.full_name)],
            students=[
                SeedStudent(email=sv.email, full_name=sv.full_name, student_code=sv.student_code, cohort=sv.cohort)
                for sv in seed_users.STUDENTS[start:end]
            ],
        ),
        klass=SeedClass(
            course=SeedCourse(code=spec.course_code, name=spec.course_name),
            **{
                "class": SeedClassSection(
                    name=spec.name,
                    semester=spec.semester,
                    join_code=spec.join_code,
                    lecturer_email=seed_users.LECTURERS[spec.lecturer_key].email,
                    pass_threshold=spec.pass_threshold,
                    color_thresholds={"green": 0.7, "yellow": 0.4},
                    min_sample=5,
                )
            },
            enroll_all_students=True,
            peer_opt_in_all=False,
        ),
        tree=build_tree(spec),
    )


def check_all() -> list[str]:
    """Kiểm ràng buộc nghiệp vụ của toàn bộ dữ liệu demo (users + classes). Trả danh sách lỗi (rỗng = sạch)."""
    errors: list[str] = []

    emails = [sv.email.lower() for sv in seed_users.STUDENTS] + [
        gv.email.lower() for gv in seed_users.LECTURERS.values()
    ]
    dup = sorted({e for e in emails if emails.count(e) > 1})
    if dup:
        errors.append(f"email trùng: {dup}")
    codes = [sv.student_code for sv in seed_users.STUDENTS]
    if len(codes) != len(set(codes)):
        errors.append("MSSV trùng")

    join_codes = [c.join_code for c in seed_classes.CLASSES]
    if len(join_codes) != len(set(join_codes)):
        errors.append(f"mã tham gia lớp trùng: {join_codes}")

    for spec in seed_classes.CLASSES:
        if spec.lecturer_key not in seed_users.LECTURERS:
            errors.append(f"{spec.join_code}: lecturer_key {spec.lecturer_key!r} không có trong seed_data.users")
            continue
        tree = build_tree(spec)
        keys = [n.key for n in tree.nodes]
        if len(keys) != len(set(keys)):
            errors.append(f"{spec.join_code}: key nút trùng")
        missing = {k for e in tree.edges for k in (e.from_key, e.to_key)} - set(keys)
        if missing:
            errors.append(f"{spec.join_code}: cạnh trỏ tới key không tồn tại: {sorted(missing)}")
        g = nx.DiGraph()
        g.add_nodes_from(keys)
        g.add_edges_from((e.from_key, e.to_key) for e in tree.edges)
        if not nx.is_directed_acyclic_graph(g):
            errors.append(f"{spec.join_code}: cây có chu trình: {nx.find_cycle(g)}")
        if not any(n.code == spec.root_cause_code for n in tree.nodes):
            errors.append(f"{spec.join_code}: không có nút root_cause_code={spec.root_cause_code!r}")
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


def write_db(db, bundle: SeedBundle) -> tuple[dict[str, int], object, dict[str, object], list[object]]:
    """Upsert (bỏ qua nếu đã có) toàn bộ dữ liệu mẫu của 1 lớp trong một transaction.
    Trả (số bản ghi mới tạo, id lớp, {mã nút: id nút}, [id SV] theo đúng thứ tự bundle.users.students)."""
    from sqlalchemy import select

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
            db.add(Student(user_id=user.id, student_code=sv.student_code, cohort=sv.cohort))
        student_ids.append(user.id)
    db.flush()

    c, k = bundle.klass.course, bundle.klass.class_
    class_id = uuid5(SEED_NAMESPACE, f"class/{k.join_code}")
    course = db.scalar(select(Course).where(Course.code == c.code))
    if course is None:
        course = Course(code=c.code, name=c.name, credits=c.credits)
        db.add(course)
        db.flush()
    section = db.scalar(select(ClassSection).where(ClassSection.join_code == k.join_code))
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
        raise ValueError("Lớp seed cũ có UUID khác hợp đồng API; cần xử lý dữ liệu cũ trước khi nạp lại")

    if bundle.klass.enroll_all_students:
        enrolled = set(db.scalars(select(Enrollment.student_id).where(Enrollment.class_id == section.id)))
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


def _read_back(db, join_code: str) -> tuple[object, dict[str, object], list[object]]:
    """Dùng sau write_db() để lấy id lớp, {mã nút: id nút}, [id SV theo đúng thứ tự email sv01..sv90]
    (phần đa lớp mới – không đụng write_db())."""
    from sqlalchemy import select

    from app.models.tree import ConceptNode, SkillTree
    from app.models.tree import TreeVersion as TreeVersionRow
    from app.models.users import ClassSection, Enrollment, User

    section_id = db.scalar(select(ClassSection.id).where(ClassSection.join_code == join_code))
    tree_row = db.scalar(select(SkillTree).where(SkillTree.class_id == section_id))
    latest_version_q = select(TreeVersionRow.id).where(TreeVersionRow.tree_id == tree_row.id)
    version_id = tree_row.published_version_id or db.scalar(latest_version_q.order_by(TreeVersionRow.version_no.desc()))
    node_rows = db.scalars(select(ConceptNode).where(ConceptNode.version_id == version_id))
    node_code_to_id = {n.code: n.id for n in node_rows if n.code}
    student_ids = list(
        db.scalars(
            select(Enrollment.student_id)
            .join(User, User.id == Enrollment.student_id)
            .where(Enrollment.class_id == section_id)
            .order_by(User.email)
        )
    )
    return section_id, node_code_to_id, student_ids


def seed_matching(db, class_id: UUID) -> None:
    """Nạp sẵn vòng ghép cặp và dữ liệu mẫu đa dạng trạng thái (MX4) cho từng lớp."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select

    from app.models.enums import MatchStatus as M
    from app.models.peer import PeerMatchItem
    from app.services.matching import MatchingService

    svc = MatchingService(db)
    existing = list(db.scalars(svc._class_matches(class_id)))
    if not existing:
        try:
            svc.run_round(class_id, "SCHEDULED")
            existing = list(db.scalars(svc._class_matches(class_id)))
        except Exception as e:
            print(f"  [MX4] Chưa thể ghép tự động cho lớp {class_id}: {e}")
            return

    now = datetime.now(timezone.utc)
    if len(existing) >= 2:
        m1 = existing[1]
        m1.status = M.ACCEPTED
        m1.accepted_by_a = True
        m1.accepted_by_b = True
        m1.expires_at = now + timedelta(days=7)
    if len(existing) >= 3:
        m2 = existing[2]
        m2.status = M.STUDIED
        m2.accepted_by_a = True
        m2.accepted_by_b = True
        m2.studied_by_a = True
        m2.studied_by_b = True
        m2.expires_at = now + timedelta(days=2)
    if len(existing) >= 4:
        m3 = existing[3]
        m3.status = M.STUDIED
        m3.accepted_by_a = True
        m3.accepted_by_b = True
        m3.studied_by_a = True
        m3.studied_by_b = True
        m3.expires_at = now + timedelta(days=2)
        items = list(db.scalars(select(PeerMatchItem).where(PeerMatchItem.match_id == m3.id)))
        for it in items:
            it.verified = True
            it.verified_at = now
    db.commit()


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # console Windows
    parser = argparse.ArgumentParser(description="Nạp dữ liệu demo đa lớp")
    parser.add_argument("--check", action="store_true", help="chỉ kiểm dữ liệu mẫu, không ghi CSDL")
    args = parser.parse_args(argv)

    errors = check_all()
    n_gv, n_sv, n_lop = len(seed_users.LECTURERS), len(seed_users.STUDENTS), len(seed_classes.CLASSES)
    print(f"{n_gv} GV, 1 QTV, {n_sv} SV dùng chung; {n_lop} lớp:")
    for spec in seed_classes.CLASSES:
        n = len(build_tree(spec).nodes)
        so_sv = spec.student_range[1] - spec.student_range[0]
        print(f"  - {spec.join_code} ({spec.name}): cây {n} nút, {so_sv} SV ghi danh")
    if errors:
        for e in errors:
            print(f"LỖI: {e}", file=sys.stderr)
        return 1
    if args.check:
        print("Dữ liệu mẫu hợp lệ (chế độ --check, không ghi CSDL)")
        return 0

    from app.db.session import SessionLocal

    with SessionLocal() as db:
        for spec in seed_classes.CLASSES:
            bundle = build_bundle(spec)
            created = write_db(db, bundle)
            if created["classes"]:
                class_id, node_code_to_id, student_ids = _read_back(db, spec.join_code)
                node_order = [(n.code, node_code_to_id[n.code]) for n in bundle.tree.nodes if n.code in node_code_to_id]
                seed_sessions.backfill(
                    db,
                    class_id,
                    student_ids,
                    node_order,
                    spec.root_cause_code,
                    seed=seed_of(spec.join_code),
                    scenario_type=spec.scenario_type,
                    peer_opt_in_count=spec.peer_opt_in_count,
                )
                print(f"Đã nạp {spec.join_code}: {created}; dựng lại tiến độ xong")
            else:
                print(f"Đã nạp {spec.join_code}: {created} (lớp đã có từ trước – không dựng lại tiến độ)")

            # Đảm bảo mỗi lớp đều có vòng ghép cặp và dữ liệu mẫu MX4
            class_id, _, _ = _read_back(db, spec.join_code)
            seed_matching(db, class_id)
            print(f"Đã chuẩn bị ghép cặp (MX4) cho {spec.join_code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
