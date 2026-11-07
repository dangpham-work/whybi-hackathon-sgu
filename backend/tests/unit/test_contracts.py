"""Hợp đồng dữ liệu (mục 3.1 kế hoạch): schema import được và serialize camelCase."""

from uuid import uuid4

from app.models.enums import CriterionCode, MasteryState, Verdict
from app.models.schemas.session import CriterionResult, SessionResult
from app.models.schemas.tree import Edge, Node, TreeVersion


def test_tree_contract_roundtrip():
    tv = TreeVersion(
        nodes=[Node(key="n1", title="Biến"), Node(key="n5_con_tro", title="Con trỏ")],
        edges=[Edge(from_key="n1", to_key="n5_con_tro")],
    )
    data = tv.model_dump(by_alias=True)
    assert data["edges"][0]["fromKey"] == "n1"
    assert TreeVersion.model_validate(data) == tv


def test_session_result_matches_example_5_4_4():
    r = SessionResult(
        session_id=uuid4(),
        student_id=uuid4(),
        node_id=uuid4(),
        class_id=uuid4(),
        state=MasteryState.MASTERED,
        verdict=Verdict.PASSED,
        total_score=78,
        criteria=[CriterionResult(code=CriterionCode.CORRECTNESS, weight=0.25, score=22, max=25)],
        source_pages=[45, 46],
        unlocked_nodes=["N6"],
    )
    data = r.model_dump(by_alias=True, mode="json")
    assert data["totalScore"] == 78 and data["passThreshold"] == 70
    assert data["unlockedNodes"] == ["N6"]


def test_all_30_tables_registered():
    import app.models  # noqa: F401
    from app.db.base import Base

    assert len(Base.metadata.tables) == 30
