"""check constraints theo từ điển dữ liệu 5.2.4 (C2-06)

Revision ID: c2a06b5e9d10
Revises: 1af58d747696
Create Date: 2026-10-14 20:00:00

Viết tay: autogenerate và `alembic check` không so sánh CHECK. `tests/unit/test_migrations.py` giữ model và
migration khớp tên. Danh sách giá trị enum chụp tại thời điểm này – thêm giá trị enum thì tạo migration mới.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c2a06b5e9d10"
down_revision: str | None = "1af58d747696"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECKS: list[tuple[str, str, str]] = [
    # Bảng 5.7 – class_node_stats
    ("class_node_stats", "ck_class_node_stats_pass_rate_range", "pass_rate IS NULL OR pass_rate BETWEEN 0 AND 1"),
    ("class_node_stats", "ck_class_node_stats_passed_le_attempted", "passed_count <= attempted_count"),
    # Bảng 5.6 – evaluations
    ("evaluations", "ck_evaluations_total_score_range", "total_score BETWEEN 0 AND 100"),
    ("evaluations", "ck_evaluations_verdict_valid", "verdict IN ('PASSED', 'FAILED')"),
    # Bảng 5.3 – mastery_records (ma trận thành thạo, 5.2.6)
    (
        "mastery_records",
        "ck_mastery_records_best_score_range",
        "best_score IS NULL OR best_score BETWEEN 0 AND 100",
    ),
    (
        "mastery_records",
        "ck_mastery_records_state_valid",
        "state IN ('LOCKED', 'AVAILABLE', 'IN_PROGRESS', 'MASTERED', 'NOT_PASSED', 'NEEDS_REVERIFY')",
    ),
    ("mastery_records", "ck_mastery_records_attempts_non_negative", "attempts >= 0"),
    # Bảng 5.8 – peer_matches
    ("peer_matches", "ck_peer_matches_distinct_students", "student_a_id <> student_b_id"),
    # 5.2.5 – prerequisite_edges (no_self_loop đã có ở migration đầu)
    (
        "prerequisite_edges",
        "ck_prerequisite_edges_confidence_range",
        "confidence IS NULL OR confidence BETWEEN 0 AND 1",
    ),
    ("rubrics", "ck_rubrics_pass_threshold_range", "pass_threshold BETWEEN 0 AND 100"),
    # Bảng 5.5 – session_turns
    (
        "session_turns",
        "ck_session_turns_stt_confidence_range",
        "stt_confidence IS NULL OR stt_confidence BETWEEN 0 AND 1",
    ),
    ("session_turns", "ck_session_turns_paste_ratio_range", "paste_ratio IS NULL OR paste_ratio BETWEEN 0 AND 1"),
    ("session_turns", "ck_session_turns_turn_no_positive", "turn_no >= 1"),
]


def upgrade() -> None:
    for table, name, condition in CHECKS:
        op.create_check_constraint(op.f(name), table, condition)


def downgrade() -> None:
    for table, name, _ in reversed(CHECKS):
        op.drop_constraint(op.f(name), table, type_="check")
