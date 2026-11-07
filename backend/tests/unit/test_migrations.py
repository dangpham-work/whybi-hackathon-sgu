"""C2-06 – Xong khi: migration chạy sạch trên máy mới.

Phần tĩnh chạy mọi nơi. Phần cần Postgres chỉ chạy khi có `TEST_DATABASE_URL` (CI job backend đặt sẵn) –
CSDL đó phải đã `alembic upgrade head`.
"""

import os
import re
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

import app.models  # noqa: F401
from app.db.base import Base
from app.models.enums import MasteryState

BACKEND = Path(__file__).resolve().parents[2]

# Ràng buộc từ điển dữ liệu 5.2.4 / 5.2.5 (tên sau quy ước NAMING ở app/db/base.py)
EXPECTED_CHECKS = {
    "mastery_records": {
        "ck_mastery_records_attempts_non_negative",
        "ck_mastery_records_best_score_range",
        "ck_mastery_records_state_valid",
    },
    "evaluations": {"ck_evaluations_total_score_range", "ck_evaluations_verdict_valid"},
    "session_turns": {
        "ck_session_turns_stt_confidence_range",
        "ck_session_turns_paste_ratio_range",
        "ck_session_turns_turn_no_positive",
    },
    "class_node_stats": {"ck_class_node_stats_pass_rate_range", "ck_class_node_stats_passed_le_attempted"},
    "prerequisite_edges": {"ck_prerequisite_edges_no_self_loop", "ck_prerequisite_edges_confidence_range"},
    "rubrics": {"ck_rubrics_pass_threshold_range"},
    "peer_matches": {"ck_peer_matches_distinct_students"},
}


def _script() -> ScriptDirectory:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(cfg)


def _check_names(table: str) -> set[str]:
    from sqlalchemy import CheckConstraint

    return {c.name for c in Base.metadata.tables[table].constraints if isinstance(c, CheckConstraint)}


def test_single_linear_history():
    script = _script()
    assert len(script.get_heads()) == 1, "nhiều head – cần alembic merge"
    revs = list(script.walk_revisions())
    assert revs[-1].down_revision is None
    assert all(not isinstance(r.down_revision, tuple | list) for r in revs), "có migration merge"


@pytest.mark.parametrize("table", sorted(EXPECTED_CHECKS))
def test_models_declare_checks(table):
    assert EXPECTED_CHECKS[table] <= _check_names(table)


def test_migration_creates_every_model_check():
    """alembic check không so CHECK – test này giữ model và migration khớp nhau."""
    text = "\n".join(p.read_text(encoding="utf-8") for p in (BACKEND / "alembic/versions").glob("*.py"))
    in_migrations = set(re.findall(r"ck_[a-z_]+", text))
    in_models = {n for t in Base.metadata.tables for n in _check_names(t)}
    assert in_models <= in_migrations, f"thiếu trong migration: {in_models - in_migrations}"


def test_mastery_state_check_lists_every_enum_value():
    from sqlalchemy import CheckConstraint

    ck = next(
        c
        for c in Base.metadata.tables["mastery_records"].constraints
        if isinstance(c, CheckConstraint) and c.name == "ck_mastery_records_state_valid"
    )
    for s in MasteryState:
        assert f"'{s.value}'" in str(ck.sqltext)


# --- Cần Postgres đã migrate ---------------------------------------------------------------------

DB_URL = os.getenv("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")


@pytest.fixture
def conn():
    from sqlalchemy import create_engine

    engine = create_engine(DB_URL)
    with engine.connect() as c:
        tx = c.begin()
        yield c
        tx.rollback()
    engine.dispose()


def _insert_mastery(conn, **overrides):
    from sqlalchemy import text

    row = {
        "id": uuid.uuid4(),
        "student_id": uuid.uuid4(),
        "node_id": uuid.uuid4(),
        "class_id": uuid.uuid4(),
        "state": "AVAILABLE",
        "attempts": 0,
        "best_score": None,
    } | overrides
    sp = conn.begin_nested()
    try:
        conn.execute(
            text(
                "INSERT INTO mastery_records"
                " (id, student_id, node_id, class_id, state, attempts, best_score, updated_at)"
                " VALUES (:id, :student_id, :node_id, :class_id, :state, :attempts, :best_score, now())"
            ),
            row,
        )
    finally:
        sp.rollback()


@needs_db
def test_db_at_head(conn):
    from sqlalchemy import text

    current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert current == _script().get_current_head()


@needs_db
def test_db_has_all_tables_and_vector(conn):
    from sqlalchemy import text

    n = conn.execute(
        text(
            "SELECT count(*) FROM information_schema.tables"
            " WHERE table_schema='public' AND table_name<>'alembic_version'"
        )
    ).scalar_one()
    assert n == 31, "30 bảng của ERD + node_review_windows (C2-15)"
    assert conn.execute(text("SELECT 1 FROM pg_extension WHERE extname='vector'")).scalar_one() == 1


@needs_db
@pytest.mark.parametrize(
    "bad",
    [{"attempts": -1}, {"state": "DONE"}, {"best_score": 101}],
    ids=["attempts_am", "state_la", "diem_qua_100"],
)
def test_db_rejects_invalid_mastery_cell(conn, bad):
    """CHECK chạy trước khóa ngoại → lỗi phải là CheckViolation."""
    from psycopg.errors import CheckViolation
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError) as exc:
        _insert_mastery(conn, **bad)
    assert isinstance(exc.value.orig, CheckViolation)


@needs_db
def test_db_valid_mastery_cell_passes_checks(conn):
    """Dòng hợp lệ vượt qua CHECK, chỉ vướng khóa ngoại (vì SV / nút giả)."""
    from psycopg.errors import ForeignKeyViolation
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError) as exc:
        _insert_mastery(conn, attempts=2, best_score=78, state="MASTERED")
    assert isinstance(exc.value.orig, ForeignKeyViolation)
