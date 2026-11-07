"""KT-11: MX3/MX4 qua API và PostgreSQL thật; bổ trợ E2E sau GD-10/GD-11.

Auth/LLM giả lập, bus trong bộ nhớ, aggregation đồng bộ. Không đo NFR-03 hoặc UI.
Fixture ma trận ghi qua MasteryService; phiên xác nhận lại chạy Orchestrator qua API.
"""

from datetime import timedelta

import pytest

from app.models.schemas.mastery import TOPIC_SESSION_COMPLETED
from app.services import heatmap, matching
from app.services.heatmap import HeatmapService
from app.services.mastery import MasteryService
from tests.unit import test_matching_db as pairs
from tests.unit import test_rootcause_db as roots
from tests.unit.test_heatmap_db import hoc

world, bus, k = pairs.world, pairs.bus, pairs.k
lop30, vi_du_6_9 = roots.lop30, roots.vi_du_6_9
pytestmark = pytest.mark.skipif(not pairs.DB_URL, reason="cần TEST_DATABASE_URL tới PostgreSQL test đã migrate")


def body(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def snapshot(w):
    w.current = w.gv
    return body(w.api.get(f"/api/v1/classes/{w.class_id}/heatmap"))


def node(snapshot_body, key):
    return next(n for n in snapshot_body["nodes"] if n["nodeKey"] == key)


def detail(w, node_id):
    w.current = w.gv
    return body(w.api.get(f"/api/v1/classes/{w.class_id}/nodes/{node_id}/detail"))


def test_heatmap_api_distinguishes_no_attempt_small_sample_and_sufficient_sample(lop30):
    w, mastery, students, ids, _ = lop30
    key = roots.N1
    first = node(snapshot(w), key)
    assert (first["color"], first["sample"], first["attemptedCount"], first["passRate"]) == (
        "GREY",
        "NO_ATTEMPT",
        0,
        None,
    )
    for student in students[:4]:
        hoc(w, mastery, student, ids[key], passed=True)
    small = node(snapshot(w), key)
    assert (small["color"], small["sample"], small["attemptedCount"], small["passedCount"]) == (
        "GREY",
        "INSUFFICIENT",
        4,
        4,
    )
    assert "Chưa đủ mẫu" in small["label"]
    hoc(w, mastery, students[4], ids[key], passed=False)
    enough = snapshot(w)
    stat = node(enough, key)
    assert (stat["color"], stat["sample"], stat["attemptedCount"], stat["passedCount"]) == ("GREEN", "SUFFICIENT", 5, 4)
    assert stat["passRate"] == pytest.approx(0.8) and "4/5" in stat["label"]
    d = detail(w, ids[key])
    assert d["stat"] == stat
    assert {s["studentId"] for s in d["studentsByState"]["NOT_PASSED"]} == {str(students[4])}
    grid = {s["studentId"]: s for s in enough["grid"]}
    assert len(grid) == 30 and all(s["studentName"] and s["studentCode"] for s in grid.values())
    assert grid[str(students[4])]["statesByKey"][key] == "NOT_PASSED"


def test_root_cause_recovery_removes_stale_alert_from_snapshot_and_detail(vi_du_6_9, monkeypatch):
    w, ids, failed = vi_du_6_9
    before = snapshot(w)
    alert = next(a for a in before["alerts"] if a["nodeKey"] == roots.N6)
    assert alert["rootCauseNodeKey"] == roots.N5
    assert alert["conditionalFailRate"] == pytest.approx(7 / 9)
    assert alert["message"] == "Nên giảng lại N5 Con trỏ"
    assert detail(w, ids[roots.N6])["alert"] == alert
    assert node(before, roots.N5)["isRootCause"] is True

    # Rút riêng cooldown để kiểm chuyển trạng thái; không chứng minh thời gian chờ hoặc SLA.
    monkeypatch.setattr("app.services.mastery.COOLDOWN", timedelta(0))
    mastery = MasteryService(w.db)
    for student in failed:
        hoc(w, mastery, student, ids[roots.N5], passed=True)
        hoc(w, mastery, student, ids[roots.N6], passed=True)
    HeatmapService(w.db).recompute_class(w.class_id)
    HeatmapService(w.db).trace_root_causes(w.class_id)
    after = snapshot(w)
    stat = node(after, roots.N6)
    assert (stat["color"], stat["attemptedCount"], stat["passedCount"]) == ("GREEN", 12, 12)
    assert stat["rootCauseNodeId"] is None and after["alerts"] == []
    assert node(after, roots.N5)["isRootCause"] is False
    d = detail(w, ids[roots.N6])
    assert d["stat"] == stat and d["alert"] is None and d["rootCauseNodeId"] is None
    assert len(d["studentsByState"]["MASTERED"]) == 12
    assert not d["studentsByState"].get("NOT_PASSED")


def opt(k, name, enabled):
    return body(k.as_(name).put(f"/api/v1/enrollments/{k.enrollment[name]}/peer-opt-in", json={"peerOptIn": enabled}))


def own_match(k, name, mid):
    rows = body(k.as_(name).get(f"/api/v1/classes/{k.w.class_id}/matches"))
    return next(m for m in rows if m["id"] == mid)


def test_example_6_6_4_includes_opted_in_student_waiting_and_student_views(k):
    # Khác fixture C2-14: Khang bật tham gia nhưng không có nút Biên để được ghép, đúng Hình 6.11.
    assert opt(k, "Khang", True) == {"peerOptIn": True}
    rnd = k.run_round()
    assert rnd["participantCount"] == 5 and len(rnd["matches"]) == 2
    assert rnd["waitingStudentIds"] == [str(k.ids["Khang"])]
    ac, dh = k.match_of(rnd, "An"), k.match_of(rnd, "Ha")
    assert {ac["studentAId"], ac["studentBId"]} == {str(k.ids[n]) for n in ("An", "Chau")}
    assert not ac["oneWay"] and dh["oneWay"]
    assert {(i["teacherId"], i["learnerId"], i["nodeKey"]) for i in ac["items"]} == {
        (str(k.ids["An"]), str(k.ids["Chau"]), pairs.N5),
        (str(k.ids["Chau"]), str(k.ids["An"]), pairs.N4),
    }
    assert all(i["teacherId"] == str(k.ids["Dung"]) and i["learnerId"] == str(k.ids["Ha"]) for i in dh["items"])
    for who, partner, teach, learn in (("An", "Chau", pairs.N5, pairs.N4), ("Chau", "An", pairs.N4, pairs.N5)):
        view = own_match(k, who, ac["id"])
        assert view["partnerId"] == str(k.ids[partner])
        assert view["iTeach"] == [teach] and view["iLearn"] == [learn]
        assert view["partnerEmail"] is None and view["status"] == "PROPOSED"
    assert body(k.as_("Khang").get(f"/api/v1/classes/{k.w.class_id}/matches")) == []


@pytest.mark.parametrize("action", ["decline", "opt_out"])
def test_decline_or_opt_out_cancels_proposal_without_changing_mastery(k, action):
    mid = k.match_of(k.run_round(), "An")["id"]
    before = snapshot(k.w)
    if action == "decline":
        assert body(k.act("An", mid, "decline"))["status"] == "DECLINED"
    else:
        assert opt(k, "An", False) == {"peerOptIn": False}
    assert own_match(k, "Chau", mid)["status"] == "DECLINED"
    rejected = k.act("Chau", mid, "accept")
    assert rejected.status_code == 409 and rejected.json()["error"]["code"] == "MATCH_INVALID_STATE"
    assert snapshot(k.w) == before


def followup(k, who, item):
    api = k.as_(who)
    created = body(
        api.post(
            "/api/v1/sessions", json={"nodeId": item["nodeId"], "inputMode": "TEXT", "peerMatchItemId": item["id"]}
        ),
        201,
    )
    sid = created["sessionId"]
    reply = body(
        api.post(
            f"/api/v1/sessions/{sid}/turns",
            json={"turnType": "EXPLANATION", "text": "Tôi giải thích khái niệm bằng ví dụ của mình."},
        )
    )
    for _ in range(5):
        if reply["status"] == "COMPLETED":
            break
        assert reply["question"] is not None
        reply = body(
            api.post(
                f"/api/v1/sessions/{sid}/turns",
                json={"turnType": "ANSWER", "text": "Tôi nêu kết quả và giải thích các bước thực hiện."},
            )
        )
    assert reply["status"] == "COMPLETED"
    return body(api.get(f"/api/v1/sessions/{sid}/result"))


@pytest.mark.parametrize(
    "pass_threshold,expected",
    [
        (70, "PASSED"),
        pytest.param(
            90,
            "FAILED",
            marks=pytest.mark.xfail(
                strict=True,
                reason="lỗi của Đăng (C1): services/session_orchestrator.py gọi Judge không truyền pass_threshold của "
                "lớp ⇒ ngưỡng GV đặt (FR-HM-08) bị bỏ qua. Sửa xong thì bỏ dấu xfail.",
            ),
        ),
    ],
)
def test_followup_sessions_update_matching_and_heatmap_consistently(k, pass_threshold, expected):
    completed, recalculated = [], []
    k.bus.subscribe(TOPIC_SESSION_COMPLETED, completed.append)
    k.bus.subscribe(TOPIC_SESSION_COMPLETED, lambda e: MasteryService(k.db, bus=k.bus).apply_result(e))
    matching.register_handlers(k.bus, session_factory=lambda: pairs._NoClose(k.db))

    def aggregate(class_id, node_id):
        hs = HeatmapService(k.db)
        recalculated.append(hs.recompute(class_id, node_id))
        hs.trace_root_causes(class_id)

    heatmap.register_handlers(k.bus, enqueue=aggregate)
    settings_url = f"/api/v1/classes/{k.w.class_id}/settings"
    settings = body(k.as_("gv").get(settings_url))
    body(k.as_("gv").put(settings_url, json=settings | {"passThreshold": pass_threshold}))
    mid = k.match_of(k.run_round(), "An")["id"]
    before = snapshot(k.w)
    for who, state in (("An", "WAITING_OTHER"), ("Chau", "ACCEPTED")):
        assert body(k.act(who, mid, "accept"))["status"] == state
    assert own_match(k, "An", mid)["partnerEmail"]
    for who, state in (("An", "ACCEPTED"), ("Chau", "STUDIED")):
        assert body(k.act(who, mid, "studied"))["status"] == state
    assert snapshot(k.w) == before, "Học cùng chưa tự chứng minh Đạt"

    for index, (who, key) in enumerate((("Chau", pairs.N5), ("An", pairs.N4)), 1):
        view = own_match(k, who, mid)
        item = next(i for i in view["items"] if i["learnerId"] == str(k.ids[who]))
        result = followup(k, who, item)
        assert result["verdict"] == expected and result["isPeerFollowup"] is True
        assert result["peerMatchItemId"] == item["id"]
        assert len(completed) == index and str(completed[-1].peer_match_item_id) == item["id"]
        updated = own_match(k, who, mid)
        verified = [i for i in updated["items"] if i["verified"]]
        assert len(verified) == (index if expected == "PASSED" else 0)
        assert updated["status"] == ("VERIFIED" if expected == "PASSED" and index == 2 else "STUDIED")
        after = snapshot(k.w)
        row = next(s for s in after["grid"] if s["studentId"] == str(k.ids[who]))
        assert row["statesByKey"][key] == ("MASTERED" if expected == "PASSED" else "NOT_PASSED")
        stat = node(after, key)
        assert stat["attemptedCount"] == 3 and stat["passedCount"] == (3 if expected == "PASSED" else 2)
        # Ô cá nhân Đạt không có nghĩa màu tổng hợp xanh: 3 người thử vẫn chưa đủ mẫu 5.
        assert stat["color"] == "GREY" and stat["sample"] == "INSUFFICIENT"
        assert detail(k.w, k.node(key))["stat"] == stat
        assert any(str(n.node_id) == item["nodeId"] for n in recalculated)
