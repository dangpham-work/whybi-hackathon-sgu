"""KT-16 – phương án dự phòng khi demo (Bảng 7.4): ngắt LLM, hết hạn mức, máy chủ khởi động lại, micro / STT lỗi.

Không gắn mark `integration`: chạy trong `uv run pytest -q`.
- Phần gateway (provider giả cấu hình lỗi) không cần CSDL – luôn chạy.
- Phần phiên giảng qua HTTP cần Postgres đã migrate (`TEST_DATABASE_URL`, CI job backend đặt sẵn); thiếu thì bỏ qua.
  Dùng lại World / cây mẫu của C1-07, C2-09 (mỗi test một transaction rollback, LLM_MODE=fake).

Provider giả ở đây đi qua `LLMGateway` THẬT (thử lại → model dự phòng → 503 LLM_UNAVAILABLE), không thay bằng một
gateway giả – để chứng minh cả chuỗi dự phòng chứ không chỉ nhánh DEMO_MODE.
Kết quả và lý do từng ca: `docs/status/quyen.md` mục KT-16.
"""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.ai.gateway import LLMGateway, reset_gateway
from app.ai.providers.base import LLMResult, PermanentProviderError, TranscriptResult, TransientProviderError
from app.ai.providers.fake import FakeProvider
from app.api.sessions import get_speech_service
from app.core.config import get_settings
from app.core.errors import AppError
from app.main import app
from app.models.schemas.admin import QuotaIn
from app.models.session import SessionTurn
from app.services.quota import QuotaService
from app.services.speech import MemoryAudioStore, SpeechService
from tests.ai.test_demo_mode import GOOD, POOR
from tests.unit import test_session_orchestrator_db as _c107
from tests.unit.test_session_orchestrator_db import DB_URL, ROOT, node_id, start, turn

# fixture dùng lại của C1-07 (gán, không import tên, để pytest thấy trong mô-đun này)
world, bus, completed, published = _c107.world, _c107.bus, _c107.completed, _c107.published

can_csdl = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

WEBM = b"\x1a\x45\xdf\xa3" + b"\0" * 64  # chỉ có chữ ký webm – đủ cho STT giả, không phải giọng nói thật


# --- provider giả cấu hình lỗi ---------------------------------------------------------------------


class ProviderSap:
    """Nhà cung cấp LLM mất kết nối: mọi lời gọi ném lỗi tạm thời (timeout / 5xx) – gateway sẽ thử lại rồi bỏ."""

    def __init__(self, name: str, model: str):
        self.name, self.model, self.calls = name, model, 0

    def complete(self, messages, schema, *, model=None, temperature=0) -> LLMResult:
        self.calls += 1
        raise TransientProviderError(f"{self.name}: mất kết nối (giả lập KT-16)")

    def embed(self, texts):
        raise TransientProviderError(f"{self.name}: mất kết nối (giả lập KT-16)")


class ProviderTonToken(FakeProvider):
    """Như FakeProvider nhưng mỗi lời gọi tốn 150 token – để ngân sách token phiên chạy thật."""

    def complete(self, messages, schema, *, model="fake", temperature=0) -> LLMResult:
        r = super().complete(messages, schema, model=model, temperature=temperature)
        r.input_tokens, r.output_tokens = 100, 50
        return r


class Mau(BaseModel):
    ok: bool = True


def gateway_sap() -> LLMGateway:
    """Model chính và model dự phòng cùng sập (Bảng 7.4: "khóa API dự phòng + mô hình dự phòng" cũng hỏng)."""
    return LLMGateway(
        ProviderSap("chinh", "model-chinh"),
        ProviderSap("du-phong", "model-du-phong"),
        transient_retries=1,
        sleep=lambda _s: None,
    )


def _dung_dinh_dang_loi(r, status: int, code: str) -> dict:
    """Lỗi đúng định dạng chung `{"error": {code, message, details}}` (mục 5.4.1) – trả `details`."""
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message", "details"}, body
    assert body["error"]["code"] == code and body["error"]["message"], body
    assert isinstance(body["error"]["details"], dict)
    return body["error"]["details"]


# --- (a) LLM sập: gateway thử model dự phòng rồi mới báo 503 (không cần CSDL) ------------------------


def test_llm_sap_ca_model_du_phong_thi_gateway_bao_503_llm_unavailable():
    gw = gateway_sap()
    with pytest.raises(AppError) as e:
        gw.call_json(Mau, [{"role": "user", "content": "x"}])
    err = e.value
    assert (err.status, err.code) == (503, "LLM_UNAVAILABLE")
    # đã thử cả model chính lẫn model dự phòng, mỗi model 1 lần + 1 lần thử lại lỗi tạm thời
    assert gw.primary.calls == 2 and gw.fallback.calls == 2
    assert [(a["provider"], a["model"]) for a in err.details["attempts"]] == [
        ("chinh", "model-chinh"),
        ("du-phong", "model-du-phong"),
    ]
    assert "mất kết nối" not in str(err.details), "chi tiết lỗi nhà cung cấp chỉ ghi log, không trả client"


def test_llm_sap_khong_lam_hong_ngan_sach_token():
    """Lời gọi hỏng không bị tính token – phiên chạy tiếp ở chế độ demo không bị trừ oan ngân sách."""
    gw = gateway_sap()
    with pytest.raises(AppError):
        gw.call_json(Mau, [{"role": "user", "content": "x"}], session_id="s1")
    assert gw.tokens_used("s1") == 0


# --- (a) LLM sập trong phiên giảng (cần CSDL) ------------------------------------------------------


def _sap(monkeypatch) -> LLMGateway:
    import app.services.session_orchestrator as orch

    gw = gateway_sap()
    monkeypatch.setattr(orch, "get_gateway", lambda: gw)
    return gw


def _giang_tron(w, sid: str, loi: list[str]) -> dict:
    reply = turn(w, sid, loi[0], "EXPLANATION")
    assert reply.status_code == 200, reply.text
    body, i = reply.json(), 1
    while body["status"] != "COMPLETED":
        assert body["status"] == "CHALLENGING" and body["question"]["text"], body
        r = turn(w, sid, loi[i % len(loi)])
        assert r.status_code == 200, r.text
        body, i = r.json(), i + 1
        assert i <= 8, "vòng phản biện phải dừng"
    r = w.api.get(f"/api/v1/sessions/{sid}/result")
    assert r.status_code == 200, r.text
    return r.json()


@can_csdl
def test_demo_bat_llm_sap_phien_van_chay_tron_va_judge_ap_br03(published, completed, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    gw = _sap(monkeypatch)
    w, tree = published
    r = start(w, tree)
    assert r.status_code == 201, r.text
    assert r.json()["opening"]["text"], "câu mở đầu lưu sẵn"
    result = _giang_tron(w, r.json()["sessionId"], GOOD)
    assert gw.primary.calls > 0 and gw.fallback.calls > 0, (
        "phải thử LLM chính + dự phòng trước khi dùng nội dung lưu sẵn"
    )
    assert len(result["criteria"]) == 5 and 0 <= result["totalScore"] <= 100
    assert result["verdict"] == "PASSED", result  # giảng đủ ý chính ⇒ Đạt
    assert "GUARD_UNCHECKED" in result["flags"], "Guard không kiểm được khi LLM sập ⇒ để lại dấu cho GV xem lại"
    assert completed and str(completed[-1].session_id) == result["sessionId"]


@can_csdl
def test_demo_bat_llm_sap_giang_sai_van_khong_dat_theo_br03(published, monkeypatch):
    """Chấm dự phòng không được "cho Đạt hết": lời giảng thiếu ý bắt buộc ⇒ FAILED (BR-03)."""
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    _sap(monkeypatch)
    w, tree = published
    sid = start(w, tree).json()["sessionId"]
    result = _giang_tron(w, sid, POOR)
    assert result["verdict"] == "FAILED", result
    assert "REQUIRED_POINTS" in result["failedConditions"], result


@can_csdl
def test_demo_tat_llm_sap_bat_dau_phien_bao_503_dung_dinh_dang(published, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_mode", False)
    _sap(monkeypatch)
    w, tree = published
    details = _dung_dinh_dang_loi(start(w, tree), 503, "LLM_UNAVAILABLE")
    assert {a["provider"] for a in details["attempts"]} == {"chinh", "du-phong"}
    # phiên hỏng câu mở đầu được tính là bỏ dở – SV bắt đầu lại được ngay khi LLM sống lại, không kẹt IN_PROGRESS
    import app.services.session_orchestrator as orch

    monkeypatch.setattr(orch, "get_gateway", lambda: LLMGateway(FakeProvider()))
    assert start(w, tree).status_code == 201


@can_csdl
def test_demo_tat_llm_sap_giua_phien_bao_503_va_khong_mat_trang_thai(published, monkeypatch):
    import app.services.session_orchestrator as orch

    monkeypatch.setattr(get_settings(), "demo_mode", False)
    w, tree = published
    sid = start(w, tree).json()["sessionId"]
    assert turn(w, sid, GOOD[0], "EXPLANATION").status_code == 200
    truoc = w.api.get(f"/api/v1/sessions/{sid}").json()

    monkeypatch.setattr(orch, "get_gateway", lambda: gateway_sap())
    _dung_dinh_dang_loi(turn(w, sid, GOOD[1]), 503, "LLM_UNAVAILABLE")
    sau = w.api.get(f"/api/v1/sessions/{sid}").json()
    assert sau == truoc, "lượt hỏng không được ghi nửa chừng; câu hỏi và hạn trả lời giữ nguyên"

    monkeypatch.setattr(orch, "get_gateway", lambda: LLMGateway(FakeProvider()))
    r = turn(w, sid, GOOD[1])  # LLM sống lại ⇒ gửi lại đúng câu trả lời đó là được
    assert r.status_code == 200 and r.json()["questionsAsked"] == truoc["questionsAsked"] + 1, r.text


# --- (b) hết hạn mức -------------------------------------------------------------------------------


def _so_luot(w, sid: str) -> int:
    return w.db.query(SessionTurn).filter_by(session_id=UUID(sid)).count()


@can_csdl
def test_het_ngan_sach_token_phien_bao_429_va_khong_mat_trang_thai(published, monkeypatch):
    import app.services.session_orchestrator as orch

    gw = LLMGateway(ProviderTonToken(), cache_size=0, token_budget=10**9)
    monkeypatch.setattr(orch, "get_gateway", lambda: gw)
    w, tree = published
    sid = start(w, tree).json()["sessionId"]
    assert turn(w, sid, GOOD[0], "EXPLANATION").status_code == 200
    truoc, luot = w.api.get(f"/api/v1/sessions/{sid}").json(), _so_luot(w, sid)

    gw.token_budget = gw.tokens_used(sid)  # lời gọi LLM kế tiếp vượt ngân sách
    details = _dung_dinh_dang_loi(turn(w, sid, GOOD[1]), 429, "TOKEN_BUDGET_EXCEEDED")
    assert details["sessionId"] == sid and details["used"] >= details["budget"]
    assert w.api.get(f"/api/v1/sessions/{sid}").json() == truoc and _so_luot(w, sid) == luot

    gw.token_budget = 10**9  # QTV nâng ngân sách (LLM_SESSION_TOKEN_BUDGET) ⇒ phiên chạy tiếp từ đúng chỗ dừng
    r = turn(w, sid, GOOD[1])
    assert r.status_code == 200 and r.json()["questionsAsked"] == truoc["questionsAsked"] + 1, r.text


@can_csdl
def test_het_ngan_sach_token_sv_bat_dau_lai_duoc(published, monkeypatch):
    """FRIENDLY.TOKEN_BUDGET_EXCEEDED bảo SV "Hãy bắt đầu phiên mới" – SV phải bắt đầu lại được ở nút đó."""
    import app.services.session_orchestrator as orch

    gw = LLMGateway(ProviderTonToken(), cache_size=0, token_budget=10**9)
    monkeypatch.setattr(orch, "get_gateway", lambda: gw)
    w, tree = published
    sid = start(w, tree).json()["sessionId"]
    assert turn(w, sid, GOOD[0], "EXPLANATION").status_code == 200
    gw.token_budget = gw.tokens_used(sid)
    assert turn(w, sid, GOOD[1]).status_code == 429
    gw.token_budget = 10**9  # phiên MỚI có ngân sách riêng
    r = start(w, tree)
    assert r.status_code == 201, r.text


@can_csdl
def test_het_han_muc_token_cua_sv_bao_429_quota_exceeded_va_khong_mat_trang_thai(published):
    """Hạn mức QTV (C2-18) chạm trần giữa phiên ⇒ 429 QUOTA_EXCEEDED, phiên giữ nguyên; nâng hạn mức là chạy tiếp"""
    w, tree = published
    sid = start(w, tree).json()["sessionId"]
    assert turn(w, sid, GOOD[0], "EXPLANATION").status_code == 200
    truoc, luot = w.api.get(f"/api/v1/sessions/{sid}").json(), _so_luot(w, sid)

    QuotaService(w.db).set(QuotaIn(scope="STUDENT", scope_id=w.sv, token_limit=0))
    details = _dung_dinh_dang_loi(turn(w, sid, GOOD[1]), 429, "QUOTA_EXCEEDED")
    assert details["kind"] == "TOKENS" and details["scope"] == "STUDENT"
    assert w.api.get(f"/api/v1/sessions/{sid}").json() == truoc and _so_luot(w, sid) == luot

    QuotaService(w.db).set(QuotaIn(scope="STUDENT", scope_id=w.sv, token_limit=None))
    assert turn(w, sid, GOOD[1]).status_code == 200


# --- (c) máy chủ khởi động lại giữa phiên -----------------------------------------------------------


@can_csdl
def test_may_chu_khoi_dong_lai_giua_phan_bien_khoi_phuc_du_phien(published, completed):
    w, tree = published
    sid = start(w, tree).json()["sessionId"]
    first = turn(w, sid, GOOD[0], "EXPLANATION").json()
    second = turn(w, sid, GOOD[1]).json()
    assert second["status"] == "CHALLENGING" and second["question"]["deadline"]

    # "khởi động lại": bỏ mọi trạng thái trong RAM (gateway, cache, đếm token, bản đồ đối tượng ORM), client mới
    reset_gateway()
    w.db.expunge_all()
    w.api = TestClient(app)

    r = w.api.get(f"/api/v1/sessions/{sid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "CHALLENGING"
    assert [(t["speaker"], t["turnType"]) for t in body["turns"]] == [
        ("TUTEE", "OPENING"),
        ("STUDENT", "EXPLANATION"),
        ("TUTEE", "QUESTION"),
        ("STUDENT", "ANSWER"),
        ("TUTEE", "QUESTION"),
    ]
    assert body["turns"][1]["text"] == GOOD[0] and body["turns"][2]["text"] == first["question"]["text"]
    assert body["question"]["text"] == second["question"]["text"]
    assert body["question"]["deadline"] == second["question"]["deadline"], "đồng hồ đếm giờ khôi phục đúng hạn cũ"
    assert (body["questionsAsked"], body["questionsTotal"]) == (second["questionsAsked"], second["questionsTotal"])

    # chạy tiếp tới kết quả bằng client mới
    reply, i = second, 2
    while reply["status"] != "COMPLETED":
        r = turn(w, sid, GOOD[i % len(GOOD)])
        assert r.status_code == 200, r.text
        reply, i = r.json(), i + 1
        assert i <= 8
    assert w.api.get(f"/api/v1/sessions/{sid}/result").status_code == 200
    assert len(completed) == 1, "session.completed phát đúng một lần dù máy chủ khởi động lại giữa phiên"


# --- (d) micro / STT lỗi ⇒ mã lỗi rõ, gõ chữ vẫn gửi được --------------------------------------------


class SttSap:
    name = "stt-sap"

    def __init__(self, exc: Exception):
        self.exc = exc

    def transcribe(self, audio, lang="vi", hints=None):
        raise self.exc


class SttIm:
    """STT chạy nhưng không nghe được gì (phòng ồn / micro tắt tiếng)."""

    name = "stt-im"

    def transcribe(self, audio, lang="vi", hints=None):
        return TranscriptResult(text="   ", confidence=0.0)


def _audio(w, sid, data=WEBM, name="loi-giang.webm", ctype="audio/webm"):
    return w.api.post(f"/api/v1/sessions/{sid}/audio", files={"file": (name, data, ctype)})


@can_csdl
@pytest.mark.parametrize(
    ("stt", "data", "status", "code"),
    [
        (SttSap(TransientProviderError("timeout")), WEBM, 503, "STT_UNAVAILABLE"),
        (SttSap(PermanentProviderError("401 sai khóa")), WEBM, 503, "STT_UNAVAILABLE"),
        (SttIm(), WEBM, 422, "NO_SPEECH_DETECTED"),
        (None, b"khong phai tep am thanh", 415, "UNSUPPORTED_AUDIO_FORMAT"),
        (None, b"RIFF\x00\x00\x00\x00WAVEhong", 415, "UNSUPPORTED_AUDIO_FORMAT"),
        (None, b"", 422, "EMPTY_AUDIO"),
    ],
    ids=["stt-tam-loi", "stt-loi-co-dinh", "khong-nghe-thay", "tep-la", "wav-hong", "tep-rong"],
)
def test_stt_loi_hoac_audio_hong_bao_ma_ro_va_go_chu_van_gui_duoc(published, monkeypatch, stt, data, status, code):
    from app.ai.providers.stt import FakeSTTProvider

    monkeypatch.setitem(
        app.dependency_overrides,
        get_speech_service,
        lambda: SpeechService(stt=stt or FakeSTTProvider(), store=MemoryAudioStore()),
    )
    w, tree = published
    r0 = w.api.post("/api/v1/sessions", json={"nodeId": node_id(tree, ROOT), "inputMode": "VOICE"})
    assert r0.status_code == 201, r0.text
    sid = r0.json()["sessionId"]

    _dung_dinh_dang_loi(_audio(w, sid, data), status, code)
    state = w.api.get(f"/api/v1/sessions/{sid}").json()
    assert state["status"] == "EXPLAINING" and len(state["turns"]) == 1, "ghi âm hỏng không được đổi trạng thái phiên"

    # SV-04 gợi ý gõ chữ ⇒ lượt văn bản trong CÙNG phiên giọng nói vẫn được nhận
    r = w.api.post(
        f"/api/v1/sessions/{sid}/turns", json={"turnType": "EXPLANATION", "text": GOOD[0], "inputMode": "TEXT"}
    )
    assert r.status_code == 200 and r.json()["status"] == "CHALLENGING", r.text
