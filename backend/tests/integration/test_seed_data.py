"""KT-02 – kiểm dữ liệu mẫu seed/ mà không cần Docker / CSDL.

Đọc seed/*.json qua `scripts/seed_db.py` (dùng schema hợp đồng `app/models/schemas/tree.py`)
và kiểm: parse được, cây là DAG, có N5 "Con trỏ", đủ 30 SV, email / MSSV duy nhất.
"""

import copy
import importlib.util
from pathlib import Path

import networkx as nx
import pytest

from app.models.schemas.tree import Edge, TreeVersion

ROOT = Path(__file__).resolve().parents[3]


def _load_seed_module():
    spec = importlib.util.spec_from_file_location("seed_db", ROOT / "scripts" / "seed_db.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed_db = _load_seed_module()


@pytest.fixture(scope="module")
def bundle():
    return seed_db.load_seed()


def test_seed_parse_duoc_bang_schema(bundle):
    assert isinstance(bundle.tree, TreeVersion)
    assert bundle.klass.class_.join_code == "CTDL2026"
    assert bundle.klass.course.name == "Cấu trúc dữ liệu và Giải thuật"


def test_cay_khop_11_nut_da_chot_va_la_dag(bundle):
    tree = bundle.tree
    assert len(tree.nodes) == 11  # Điều phối duyệt giữ cây C2-02 đã merge, gồm AVL.
    keys = [n.key for n in tree.nodes]
    assert len(keys) == len(set(keys)), "key nút phải duy nhất"
    g = nx.DiGraph()
    g.add_nodes_from(keys)
    g.add_edges_from((e.from_key, e.to_key) for e in tree.edges)
    assert set(g.nodes) == set(keys), "cạnh trỏ tới key không tồn tại"
    assert nx.is_directed_acyclic_graph(g)


def test_co_nut_n5_con_tro_voi_rubric_da_duyet(bundle):
    n5 = next(n for n in bundle.tree.nodes if n.code == "N5")
    assert n5.title == "Con trỏ"
    assert n5.rubric is not None and n5.rubric.approved
    assert len(n5.rubric.key_points) >= 3
    assert any(m.is_critical for m in n5.rubric.misconceptions)
    assert len(n5.rubric.scenarios) >= n5.rubric.min_challenges


def test_du_1_gv_1_qtv_30_sv(bundle):
    assert len(bundle.users.lecturers) == 1
    assert len(bundle.users.admins) == 1
    assert len(bundle.users.students) == 30


def test_email_va_mssv_duy_nhat(bundle):
    emails = [u.email.lower() for u in bundle.users.all_accounts()]
    assert len(emails) == len(set(emails))
    codes = [s.student_code for s in bundle.users.students]
    assert len(codes) == len(set(codes))


def test_tai_khoan_demo_khop_kich_ban(bundle):
    # docs/demo-script.md: GV gv@whybi.test, SV sv01 (An), sv02 (Châu)
    by_email = {u.email: u for u in bundle.users.all_accounts()}
    assert bundle.klass.class_.lecturer_email in {gv.email for gv in bundle.users.lecturers}
    assert by_email["sv01@whybi.test"].full_name.endswith("An")
    assert by_email["sv02@whybi.test"].full_name.endswith("Châu")


def test_check_seed_sach(bundle):
    assert seed_db.check_seed(bundle) == []


def test_check_seed_bat_chu_trinh(bundle):
    broken = copy.deepcopy(bundle)
    broken.tree.edges.append(Edge(from_key="n6_cap_phat_dong", to_key="n5_con_tro"))  # TC03
    errors = seed_db.check_seed(broken)
    assert any("chu trình" in e for e in errors)


def test_check_seed_bat_email_trung(bundle):
    broken = copy.deepcopy(bundle)
    broken.users.students[1].email = broken.users.students[0].email
    errors = seed_db.check_seed(broken)
    assert any("email" in e for e in errors)


def test_sample_syllabi_include_pdf_docx_and_image_only_pdf():
    import zipfile

    import pymupdf

    directory = ROOT / "seed" / "syllabi"
    with pymupdf.open(directory / "01_ctdl_digital.pdf") as pdf:
        assert "Con trỏ" in "".join(page.get_text() for page in pdf)
    with zipfile.ZipFile(directory / "02_ctdl_notes.docx") as document:
        assert "Danh sách liên kết" in document.read("word/document.xml").decode("utf-8")
    with pymupdf.open(directory / "03_ctdl_scan.pdf") as pdf:
        assert all(not page.get_text().strip() and page.get_images() for page in pdf)


def test_seed_db_keeps_api_ids_rubric_fields_and_is_idempotent(bundle):
    import os

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.models import tree as orm
    from app.models.users import ClassSection
    from app.services.skill_tree import SEED_CLASS_ID, load_seed_tree

    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("requires migrated Postgres")
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                created = seed_db.write_db(db, bundle)
                section = db.scalar(select(ClassSection).where(ClassSection.join_code == "CTDL2026"))
                assert section.id == SEED_CLASS_ID
                tree = db.scalar(select(orm.SkillTree).where(orm.SkillTree.class_id == section.id))
                version = db.scalar(select(orm.TreeVersion).where(orm.TreeVersion.tree_id == tree.id))
                assert version.id == load_seed_tree().id
                assert version.status == bundle.tree.status.value
                expected_published = version.id if bundle.tree.status.value == "PUBLISHED" else None
                assert tree.published_version_id == expected_published
                expected = next(n for n in load_seed_tree().nodes if n.code == "N5")
                node = db.scalar(
                    select(orm.ConceptNode).where(
                        orm.ConceptNode.version_id == version.id, orm.ConceptNode.key == expected.key
                    )
                )
                assert node.id == expected.id and node.code == expected.code
                rubric = db.scalar(select(orm.Rubric).where(orm.Rubric.node_id == node.id))
                assert rubric.source_pages == expected.rubric.source_pages
                assert rubric.optional_points == expected.rubric.optional_points
                assert rubric.target_bloom == expected.rubric.target_bloom
                assert rubric.min_passed_challenges == expected.rubric.min_passed_challenges
                points = list(db.scalars(select(orm.KeyPoint).where(orm.KeyPoint.node_id == node.id)))
                assert {p.code for p in points} == {p.id for p in expected.rubric.key_points}
                scenarios = list(
                    db.scalars(select(orm.ChallengeScenario).where(orm.ChallengeScenario.node_id == node.id))
                )
                assert {s.code: s.expected_points for s in scenarios} == {
                    s.id: s.expected_points for s in expected.rubric.scenarios
                }
                assert created["users"] == 32
                assert all(value == 0 for value in seed_db.write_db(db, bundle).values())
        finally:
            transaction.rollback()
    engine.dispose()
