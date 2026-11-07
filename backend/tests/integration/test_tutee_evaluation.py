"""KT-12: lần sinh đầu, nhãn người chấm và giới hạn của số liệu fake."""

import copy
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SAFE = "Mình chưa hình dung được tình huống này. Bạn cho mình một ví dụ được không?"
LEAK = "Con trỏ là biến lưu địa chỉ của một ô nhớ, đúng không?"


@pytest.fixture(scope="module")
def kt12():
    spec = importlib.util.spec_from_file_location("kt12_evaluate", ROOT / "evals/tutee/evaluate.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_30_kich_ban_doc_lap_chua_co_nhan(kt12):
    cases = kt12.load_scenarios()
    assert len(cases) == len({c.id for c in cases}) == 30
    assert {c.node for c in cases} == {"N5"}
    assert len({c.student_turns[0] for c in cases}) == 30
    assert {c.group for c in cases} == set(kt12.GROUPS)
    assert all(c.source == "ai_draft" and len(c.student_turns) == 4 for c in cases)


@pytest.mark.parametrize("defect", ["duplicate", "empty", "unknown_node", "blank", "unknown_field"])
def test_du_lieu_hong_bi_tu_choi_truoc_llm(kt12, tmp_path, defect):
    rows = [kt12.load_scenarios()[0].model_dump()]
    if defect == "duplicate":
        rows *= 2
    elif defect == "empty":
        rows = []
    elif defect == "unknown_node":
        rows[0]["node"] = "N999"
    elif defect == "blank":
        rows[0]["student_turns"][0] = "   "
    else:
        rows[0]["leak_annotations"] = []
    path = tmp_path / "cases.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    with pytest.raises(ValueError):
        kt12.load_scenarios(path)


class GatewayScript:
    def __init__(self, texts):
        self.texts = iter(texts)

    def call_json(self, schema, messages, **kwargs):
        from app.ai.agents.guard import LeakVerdict
        from app.ai.agents.tutee import TuteeUtterance

        if schema is TuteeUtterance:
            return schema(question=next(self.texts))
        if schema is LeakVerdict:
            return schema(leaks=False)
        raise AssertionError(schema)


@pytest.mark.parametrize(
    "texts,attempts,fallback", [([SAFE], 1, False), ([LEAK, SAFE], 2, False), ([LEAK] * 3, 3, True)]
)
def test_quan_sat_guard_giu_nguyen_quyet_dinh(kt12, texts, attempts, fallback):
    from app.ai.agents.tutee import TuteeAgent
    from app.services.skill_tree import load_seed_tree

    gw = GatewayScript(texts)
    guard = kt12.RecordingGuard(gw)
    node = next(n for n in load_seed_tree().nodes if n.code == "N5")
    guard.question_id = "T01:opening"
    result = TuteeAgent(gw, guard=guard).opening_line(node)
    observed = guard.records[0]
    assert observed["attempts"] == attempts and observed["used_fallback"] is fallback
    assert observed["first_pass"] is (attempts == 1 and not fallback)
    assert len(observed["drafts"]) == attempts
    assert observed["final_text"] == result.text and observed["drafts"][0]["text"] == texts[0]
    if attempts > 1:
        assert observed["drafts"][1]["feedback"]


def test_loi_guard_khong_tinh_la_qua_lan_dau(kt12):
    from app.ai.agents.tutee import TuteeAgent
    from app.core.errors import AppError
    from app.services.skill_tree import load_seed_tree

    class Broken(GatewayScript):
        def call_json(self, schema, messages, **kwargs):
            from app.ai.agents.guard import LeakVerdict

            if schema is LeakVerdict:
                raise AppError(503, "LLM_UNAVAILABLE", "Unavailable")
            return super().call_json(schema, messages, **kwargs)

    gw = Broken([SAFE])
    guard = kt12.RecordingGuard(gw)
    with pytest.raises(AppError):
        TuteeAgent(gw, guard=guard).opening_line(next(n for n in load_seed_tree().nodes if n.code == "N5"))
    assert guard.records[0]["error"] == "LLM_UNAVAILABLE"
    assert guard.records[0]["first_pass"] is False and guard.records[0]["final_text"] is None


@pytest.fixture
def complete_run():
    sessions = []
    for i in range(30):
        sid = f"T{i + 1:02}"
        sessions.append(
            {
                "id": sid,
                "node": "N5",
                "group": "correct",
                "source": "ai_draft",
                "error": None,
                "questions": [
                    {
                        "question_id": f"{sid}:{j}",
                        "final_text": f"{SAFE} {i}-{j}",
                        "first_pass": True,
                        "attempts": 1,
                        "used_fallback": False,
                        "error": None,
                    }
                    for j in range(4)
                ],
            }
        )
    return {
        "schema_version": 1,
        "run_id": "test-run",
        "mode": "real",
        "target_sessions": 30,
        "sessions": sessions,
        "gateway_calls": [{"provider": "gemini", "model": "test", "outcome": "ok"}],
    }


def human_review(kt12, run, leak_count=0):
    review = kt12.draft_review(run)
    review.update(source="human", reviewer="Người chấm thử trong test")
    for i, label in enumerate(review["labels"]):
        label["leak"] = i < leak_count
    return review


def test_nhan_pending_khong_bien_thanh_khong_lo(kt12, complete_run):
    review = kt12.draft_review(complete_run)
    assert all(label["leak"] is None for label in review["labels"])
    result = kt12.summarize(complete_run, review)
    assert result["leak_rate"] is None and result["status"] == "NEEDS_REVIEW"
    assert result["first_pass_rate"] == 1


@pytest.mark.parametrize("bad_first,leaks,status", [(6, 6, "PASSED"), (7, 6, "FAILED"), (6, 7, "FAILED")])
def test_nguong_95_va_5_phan_tram(kt12, complete_run, bad_first, leaks, status):
    for q in [q for s in complete_run["sessions"] for q in s["questions"]][:bad_first]:
        q.update(first_pass=False, attempts=2)
    result = kt12.summarize(complete_run, human_review(kt12, complete_run, leaks))
    assert result["first_pass_rate"] == (120 - bad_first) / 120
    assert result["leak_rate"] == leaks / 120 and result["status"] == status


@pytest.mark.parametrize("defect", ["missing_session", "error", "missing_question", "fake"])
def test_thieu_du_lieu_hoac_fake_khong_ket_luan_dat(kt12, complete_run, defect):
    if defect == "missing_session":
        complete_run["sessions"].pop()
    elif defect == "error":
        complete_run["sessions"][0]["error"] = "LLM_UNAVAILABLE"
    elif defect == "missing_question":
        complete_run["sessions"][0]["questions"].pop()
    else:
        complete_run["mode"] = "fake"
    result = kt12.summarize(complete_run, human_review(kt12, complete_run))
    assert result["status"] == ("SIMULATION" if defect == "fake" else "INCOMPLETE")


@pytest.mark.parametrize(
    "defect",
    ["run_id", "text", "missing", "duplicate", "string_label", "no_reviewer", "null_reviewer", "number_reviewer"],
)
def test_khong_nhan_nhan_cu_hay_sai_dinh_dang(kt12, complete_run, defect):
    review = human_review(kt12, complete_run)
    if defect == "run_id":
        review["run_id"] = "other-run"
    elif defect == "text":
        complete_run["sessions"][0]["questions"][0]["final_text"] = "Câu đã đổi?"
    elif defect == "missing":
        review["labels"].pop()
    elif defect == "duplicate":
        review["labels"].append(copy.deepcopy(review["labels"][0]))
    elif defect == "string_label":
        review["labels"][0]["leak"] = "false"
    elif defect == "no_reviewer":
        review["reviewer"] = ""
    else:
        review["reviewer"] = None if defect == "null_reviewer" else 42
    with pytest.raises(ValueError):
        kt12.summarize(complete_run, review)


def test_collect_fake_30_phien_120_cau_va_nhan_pending(kt12):
    from app.ai.gateway import LLMGateway
    from app.ai.providers.fake import FakeProvider

    run = kt12.collect(kt12.load_scenarios(), LLMGateway(FakeProvider(), cache_size=0), mode="fake")
    assert len(run["sessions"]) == 30
    assert all(len(s["questions"]) == 4 and not s["error"] for s in run["sessions"])
    assert len(kt12.draft_review(run)["labels"]) == 120
    assert kt12.summarize(run)["status"] == "SIMULATION"


def test_khong_ghi_de_luot_cu(kt12, complete_run, tmp_path):
    out = tmp_path / "run"
    kt12.write_outputs(complete_run, out)
    before = (out / "run.json").read_bytes()
    with pytest.raises(FileExistsError):
        kt12.write_outputs(complete_run, out)
    assert (out / "run.json").read_bytes() == before


def test_khong_nhan_gateway_fake_cho_luot_do_that(kt12):
    from app.ai.gateway import LLMGateway
    from app.ai.providers.fake import FakeProvider

    with pytest.raises(ValueError, match="fake"):
        kt12.collect(kt12.load_scenarios()[:1], LLMGateway(FakeProvider()), mode="real")


def test_khong_dung_fallback_fake_de_gia_lam_so_lieu_that(kt12, complete_run):
    from types import SimpleNamespace

    gateway = SimpleNamespace(primary=SimpleNamespace(name="gemini"), fallback=SimpleNamespace(name="fake"))
    with pytest.raises(ValueError, match="fake"):
        kt12.collect(kt12.load_scenarios()[:1], gateway, mode="real")
    complete_run["gateway_calls"].append({"provider": "fake"})
    with pytest.raises(ValueError, match="fake"):
        kt12.summarize(complete_run)


def test_loi_sinh_cau_van_co_trong_mau_so(kt12):
    from app.ai.agents.tutee import TuteeAgent
    from app.core.errors import AppError
    from app.services.skill_tree import load_seed_tree

    class Broken:
        def call_json(self, *args, **kwargs):
            raise AppError(503, "LLM_UNAVAILABLE", "Unavailable")

    gw = Broken()
    guard = kt12.RecordingGuard(gw)
    with pytest.raises(AppError):
        TuteeAgent(gw, guard=guard).opening_line(next(n for n in load_seed_tree().nodes if n.code == "N5"))
    assert guard.records[0]["attempts"] == 1 and guard.records[0]["first_pass"] is False
    assert guard.records[0]["drafts"][0]["error"] == "LLM_UNAVAILABLE"


def test_cli_tu_choi_demo_va_ngan_sach_that_truoc_khi_goi_gateway(kt12, tmp_path, monkeypatch):
    import app.ai.gateway as gateway_mod
    from app.core.config import get_settings

    def forbidden(*args, **kwargs):
        pytest.fail("Không được gọi gateway khi preflight chưa hợp lệ")

    monkeypatch.setattr(gateway_mod, "build_gateway", forbidden)
    settings = get_settings()
    monkeypatch.setattr(settings, "demo_mode", True)
    assert kt12.main(["collect", "--output", str(tmp_path / "demo")]) == 2
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "llm_mode", "real")
    assert kt12.main(["collect", "--output", str(tmp_path / "real"), "--limit", "30"]) == 2
    assert not (tmp_path / "real").exists()


def test_cli_fake_chay_thu_khong_ghi_ket_qua_chinh_thuc(kt12, tmp_path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "llm_mode", "fake")
    monkeypatch.setattr(get_settings(), "demo_mode", False)
    official = ROOT / "evals/results/tutee.md"
    before = official.read_bytes()
    out = tmp_path / "partial"
    assert kt12.main(["collect", "--output", str(out), "--limit", "1"]) == 1
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert run["mode"] == "fake" and run["gateway_calls"]
    assert {c["provider"] for c in run["gateway_calls"]} == {"fake"}
    assert run["provenance"]["scenario_digest"]
    assert "SIMULATION" in (out / "summary.md").read_text(encoding="utf-8")
    assert official.read_bytes() == before


def test_bang_chung_giu_dung_cay_rubric_thuc_te_da_dung(kt12, monkeypatch):
    from app.ai.gateway import LLMGateway
    from app.ai.providers.fake import FakeProvider

    cases = kt12.load_scenarios()[:1]
    tree = kt12.load_seed_tree().model_copy(deep=True)
    node = next(n for n in tree.nodes if n.code == "N5")
    node.title = "Con trỏ trong cây kiểm thử khác"
    monkeypatch.setattr(kt12, "load_seed_tree", lambda: tree)
    run = kt12.collect(cases, LLMGateway(FakeProvider()), mode="fake")
    assert run["nodes"]["N5"]["title"] == node.title
    assert run["nodes"]["N5"]["rubric"] == node.rubric.model_dump(mode="json")


def test_cli_in_tieng_viet_du_khi_console_khong_mac_dinh_utf8(tmp_path):
    env = dict(os.environ, APP_ENV="test", LLM_MODE="fake", DEMO_MODE="0", PYTHONIOENCODING="ascii")
    result = subprocess.run(
        [sys.executable, str(ROOT / "evals/tutee/evaluate.py"), "collect", "--output", str(tmp_path / "cli")],
        cwd=ROOT / "backend",
        env=env,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert "Dữ liệu và nhãn chờ chấm" in result.stdout.decode("utf-8")
