"""C1-07 – hợp đồng sự kiện `session.completed` và lỗi API phiên (chốt trước khi làm logic).

Bên nghe: MasteryService (Long, C2-10). Bên dùng API: Thắng (SV-04, SV-06), Quyền (KT-06).
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.enums import FlagType, MasteryState, Verdict
from app.models.schemas.mastery import TOPIC_SESSION_COMPLETED
from app.models.schemas.session import (
    NodeAlreadyMasteredDetails,
    NodeLockedDetails,
    SessionResult,
    TurnReply,
)
from app.realtime.bus import InMemoryEventBus


def test_session_completed_example_is_valid_and_roundtrips_on_bus():
    example = SessionResult.model_json_schema()["examples"][0]
    result = SessionResult.model_validate(example)
    assert result.verdict == Verdict.PASSED and result.state == MasteryState.MASTERED
    got = []
    bus = InMemoryEventBus()
    bus.subscribe(TOPIC_SESSION_COMPLETED, got.append)
    bus.publish(TOPIC_SESSION_COMPLETED, result)
    assert got == [result]


def test_session_result_failed_conditions_camelcase():
    r = SessionResult(
        session_id=uuid4(),
        student_id=uuid4(),
        node_id=uuid4(),
        class_id=uuid4(),
        state=MasteryState.NOT_PASSED,
        verdict=Verdict.FAILED,
        total_score=82,
        criteria=[],
        failed_conditions=["REQUIRED_POINTS"],
    )
    data = r.model_dump(by_alias=True, mode="json")
    assert data["failedConditions"] == ["REQUIRED_POINTS"] and data["attemptNo"] == 1


def test_turn_reply_flags():
    r = TurnReply(status="CHALLENGING", flags=[FlagType.JAILBREAK], notice="Mình chỉ là bạn học…")
    assert r.model_dump(by_alias=True, mode="json")["flags"] == ["JAILBREAK"]


def test_node_locked_details_lists_missing_prerequisite_keys():
    """TC06: details chỉ mang key nút tiên quyết còn thiếu (ổn định giữa các phiên bản cây, mục 5.2.5)."""
    d = NodeLockedDetails(
        node_id=uuid4(),
        state=MasteryState.LOCKED,
        missing_prerequisites=["n3_con_tro", "n4_de_quy"],
    )
    data = d.model_dump(by_alias=True, mode="json")
    assert data["state"] == "LOCKED"
    assert data["missingPrerequisites"] == ["n3_con_tro", "n4_de_quy"]


@pytest.mark.parametrize("bad", [["N4 Đệ quy"], ["n4_de_quy", "n4_de_quy"]])
def test_node_locked_details_rejects_bad_or_duplicate_keys(bad):
    with pytest.raises(ValidationError):
        NodeLockedDetails(node_id=uuid4(), state=MasteryState.LOCKED, missing_prerequisites=bad)


def test_locked_node_must_name_missing_prerequisites():
    with pytest.raises(ValidationError):
        NodeLockedDetails(node_id=uuid4(), state=MasteryState.LOCKED, missing_prerequisites=[])


@pytest.mark.parametrize(
    "state",
    [MasteryState.AVAILABLE, MasteryState.NOT_PASSED, MasteryState.NEEDS_REVERIFY, MasteryState.MASTERED],
)
def test_node_locked_details_only_for_locked_nodes(state):
    """NODE_LOCKED chỉ cho ô chưa mở. NOT_PASSED đang chờ BR-11 là RETRY_COOLDOWN, MASTERED là NODE_ALREADY_MASTERED
    (mã lỗi của MasteryService – C2-10)."""
    with pytest.raises(ValidationError):
        NodeLockedDetails(node_id=uuid4(), state=state, missing_prerequisites=["n4_de_quy"])


def test_already_mastered_details_shape():
    node_id = uuid4()
    d = NodeAlreadyMasteredDetails(node_id=node_id, state=MasteryState.MASTERED)
    assert d.model_dump(by_alias=True, mode="json") == {"nodeId": str(node_id), "state": "MASTERED"}


@pytest.mark.parametrize("state", [MasteryState.LOCKED, MasteryState.NEEDS_REVERIFY])
def test_already_mastered_details_rejects_other_states(state):
    with pytest.raises(ValidationError):
        NodeAlreadyMasteredDetails(node_id=uuid4(), state=state)


def _deref(schemas, schema):
    return schemas[schema["$ref"].split("/")[-1]] if "$ref" in schema else schema


def _const(prop):
    return prop.get("const", (prop.get("enum") or [None])[0]) if len(prop.get("enum", [0])) == 1 else None


def test_start_session_409_documents_node_locked_and_already_mastered():
    from app.main import app

    schemas = app.openapi()["components"]["schemas"]
    resp = app.openapi()["paths"]["/api/v1/sessions"]["post"]["responses"]["409"]
    root = resp["content"]["application/json"]["schema"]
    variants = root.get("anyOf") or root.get("oneOf") or [root]
    by_code = {}
    for v in variants:
        error = _deref(schemas, _deref(schemas, v)["properties"]["error"])
        by_code[_const(error["properties"]["code"])] = error["properties"]["details"]["$ref"].split("/")[-1]
    assert by_code == {"NODE_LOCKED": "NodeLockedDetails", "NODE_ALREADY_MASTERED": "NodeAlreadyMasteredDetails"}
    assert _const(schemas["NodeLockedDetails"]["properties"]["state"]) == "LOCKED"
    assert _const(schemas["NodeAlreadyMasteredDetails"]["properties"]["state"]) == "MASTERED"
    assert set(schemas["NodeAlreadyMasteredDetails"]["required"]) == {"nodeId", "state"}


def test_node_locked_details_are_reachable_from_openapi_error_response():
    from app.main import app

    document = app.openapi()
    schemas = document["components"]["schemas"]
    assert "NodeLockedDetails" in schemas
    assert "MissingPrerequisite" not in schemas
    items = schemas["NodeLockedDetails"]["properties"]["missingPrerequisites"]["items"]
    assert items["type"] == "string" and items["pattern"] == "^[a-z0-9_]+$"
    assert schemas["NodeLockedDetails"]["properties"]["missingPrerequisites"]["minItems"] == 1
    # đường từ response 409 tới NodeLockedDetails: test_start_session_409_documents_node_locked_and_already_mastered
