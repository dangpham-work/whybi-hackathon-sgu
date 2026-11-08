"""KT-02 – kiểm dữ liệu demo đa lớp (scripts/seed_data/) mà không cần Docker / CSDL.

Đọc qua `scripts/seed_db.py` (dùng schema hợp đồng `app/models/schemas/tree.py`) và kiểm: mỗi lớp build ra
cây là DAG hợp lệ, không trùng key/join_code/email/MSSV, lớp CTDL2026 vẫn giữ đúng 11 nút nền + N5 "Con trỏ"
có rubric đã duyệt (hợp đồng `app/services/skill_tree.SEED_CLASS_ID` dựa vào).
"""

import copy
import importlib.util
from pathlib import Path

import networkx as nx
import pytest

from app.models.schemas.tree import Edge

ROOT = Path(__file__).resolve().parents[3]


def _load_seed_module():
    spec = importlib.util.spec_from_file_location("seed_db", ROOT / "scripts" / "seed_db.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed_db = _load_seed_module()


def test_khong_co_loi_nghiep_vu():
    assert seed_db.check_all() == []


def test_90_sv_dung_chung_email_va_mssv_duy_nhat():
    from scripts.seed_data import users as seed_users

    assert len(seed_users.STUDENTS) == 90
    assert len(seed_users.LECTURERS) == 2
    emails = [sv.email.lower() for sv in seed_users.STUDENTS]
    assert len(emails) == len(set(emails))
    codes = [sv.student_code for sv in seed_users.STUDENTS]
    assert len(codes) == len(set(codes))


def test_5_lop_khong_trung_ma_tham_gia():
    from scripts.seed_data import classes as seed_classes

    codes = [c.join_code for c in seed_classes.CLASSES]
    assert len(codes) == len(set(codes)) == 5


def test_moi_lop_la_dag_hop_le_va_co_nut_root_cause():
    from scripts.seed_data import classes as seed_classes

    for spec in seed_classes.CLASSES:
        tree = seed_db.build_tree(spec)
        keys = [n.key for n in tree.nodes]
        assert len(keys) == len(set(keys)), spec.join_code
        g = nx.DiGraph()
        g.add_nodes_from(keys)
        g.add_edges_from((e.from_key, e.to_key) for e in tree.edges)
        assert nx.is_directed_acyclic_graph(g), spec.join_code
        assert any(n.code == spec.root_cause_code for n in tree.nodes), spec.join_code


def test_lop_ctdl2026_giu_dung_hop_dong_seed_cu():
    """Lớp mặc định của C2-02/các thẻ cũ vẫn phải khớp app.services.skill_tree.SEED_CLASS_ID."""
    from scripts.seed_data import classes as seed_classes

    spec = next(c for c in seed_classes.CLASSES if c.join_code == "CTDL2026")
    tree = seed_db.build_tree(spec)
    assert len(tree.nodes) >= 11
    n5 = next(n for n in tree.nodes if n.code == "N5")
    assert n5.title == "Con trỏ"
    assert n5.rubric is not None and n5.rubric.approved
    assert len(n5.rubric.key_points) >= 3
    assert any(m.is_critical for m in n5.rubric.misconceptions)
    assert len(n5.rubric.scenarios) >= n5.rubric.min_challenges


def test_check_all_bat_email_trung(monkeypatch):
    from scripts.seed_data import users as seed_users

    broken = copy.deepcopy(seed_users.STUDENTS)
    broken[1] = broken[1].__class__(**{**broken[1].__dict__, "email": broken[0].email})
    monkeypatch.setattr(seed_users, "STUDENTS", broken)
    assert any("email" in e for e in seed_db.check_all())


def test_check_all_bat_chu_trinh(monkeypatch):
    from scripts.seed_data import classes as seed_classes
    from scripts.seed_data import trees as seed_trees

    def build_voi_chu_trinh(spec, base=None):
        base_tree = seed_trees.fixture_tree() if spec.base == "ctdl" else None
        tv = seed_trees.build(spec.tree_spec, base=base_tree)
        if spec.join_code == seed_classes.CLASSES[0].join_code:
            tv.edges.append(Edge(from_key=tv.nodes[-1].key, to_key=tv.nodes[0].key))
        return tv

    monkeypatch.setattr(seed_db, "build_tree", build_voi_chu_trinh)
    errors = seed_db.check_all()
    assert any("chu trình" in e for e in errors)


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


def test_seed_db_keeps_api_ids_rubric_fields_and_is_idempotent():
    import os

    from scripts.seed_data import classes as seed_classes
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.models import tree as orm
    from app.models.users import ClassSection
    from app.services.skill_tree import SEED_CLASS_ID, load_seed_tree

    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("requires migrated Postgres")
    spec = next(c for c in seed_classes.CLASSES if c.join_code == "CTDL2026")
    bundle = seed_db.build_bundle(spec)
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                created = seed_db.write_db(db, bundle)
                class_id, node_code_to_id, student_ids = seed_db._read_back(db, spec.join_code)
                assert class_id == SEED_CLASS_ID
                section = db.scalar(select(ClassSection).where(ClassSection.join_code == "CTDL2026"))
                assert section.id == SEED_CLASS_ID
                tree = db.scalar(select(orm.SkillTree).where(orm.SkillTree.class_id == section.id))
                version = db.scalar(select(orm.TreeVersion).where(orm.TreeVersion.tree_id == tree.id))
                assert version.id == load_seed_tree().id
                expected = next(n for n in load_seed_tree().nodes if n.code == "N5")
                assert node_code_to_id["N5"] == expected.id
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
                u = bundle.users
                assert created["users"] == len(u.students) + len(u.lecturers) + len(u.admins)
                second = seed_db.write_db(db, bundle)
                assert all(value == 0 for value in second.values())
        finally:
            transaction.rollback()
    engine.dispose()
