"""Khung test tích hợp (KT-03): pytest + httpx gọi API thật đang chạy (docker compose hoặc CI).

Mặc định BỎ QUA mọi test gắn `@pytest.mark.integration`. Bật bằng biến môi trường:

    RUN_INTEGRATION=1 INTEGRATION_API_URL=http://localhost:8000 uv run pytest -q -m integration

- `INTEGRATION_API_URL`: gốc API (mặc định http://localhost:8000 – cổng api của docker compose).
- Khi đã bật mà API không trả lời /health → test FAIL (không bỏ qua), để CI thấy stack hỏng.
- Test không gắn mark (vd. test_seed_data.py) vẫn chạy bình thường trong `pytest -q`.
"""

import os
from collections.abc import Iterator

import httpx
import pytest

# Fixture CSDL dùng chung cho test vòng 2 / 3 (KT-14, KT-15): lớp KT-08 + phiên thật, kho ghi âm trong bộ nhớ.
from tests.integration.lop_vong import lop_vong  # noqa: F401
from tests.integration.test_bao_mat_phan_quyen_db import kho_am_thanh  # noqa: F401

RUN = os.getenv("RUN_INTEGRATION", "").lower() in {"1", "true", "yes"}
API_URL = os.getenv("INTEGRATION_API_URL", "http://localhost:8000").rstrip("/")
API_PREFIX = "/api/v1"
TIMEOUT = float(os.getenv("INTEGRATION_TIMEOUT", "10"))

_SKIP = pytest.mark.skip(reason="test tích hợp: đặt RUN_INTEGRATION=1 và chạy stack (docker compose up -d)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if RUN:
        return
    for item in items:
        if item.get_closest_marker("integration"):
            item.add_marker(_SKIP)


@pytest.fixture(scope="session")
def api_url() -> str:
    return API_URL


@pytest.fixture(scope="session")
def http() -> Iterator[httpx.Client]:
    """Client tới gốc API (không có /api/v1) – dùng cho /health, /openapi.json."""
    with httpx.Client(base_url=API_URL, timeout=TIMEOUT) as c:
        try:
            c.get("/health").raise_for_status()
        except httpx.HTTPError as exc:
            pytest.fail(f"RUN_INTEGRATION=1 nhưng API {API_URL} không sẵn sàng: {exc}")
        yield c


@pytest.fixture(scope="session")
def api(http: httpx.Client) -> Iterator[httpx.Client]:
    """Client tới {API_URL}/api/v1 – đường dẫn trong test viết như Bảng 5.10 (vd. "/auth/login")."""
    with httpx.Client(base_url=API_URL + API_PREFIX, timeout=TIMEOUT) as c:
        yield c


# --- Lỗi/thiếu sót của người khác mà test KT đã phát hiện -------------------------------------------
# xfail(strict): test vẫn chạy; khi chủ thư mục sửa xong, test XPASS làm đỏ CI ⇒ người sửa xóa dòng tương ứng ở đây.
_CHO_CAU_HINH_GIO = (
    "chờ Đăng/Long (C1-15, C2-17): Settings chưa có answer_time_limit_s; phiên mới chưa áp ngưỡng Đạt, số câu của GV"
)
_XFAIL_THEO_TEN = {
    "test_bao_mat_phan_quyen_db.py::test_sv_ngoai_lop_my_map_lop_chua_phat_hanh_bi_403": (
        "lỗi của Long (C2): services/mastery.py my_map gọi _tree() trước _require_enrolled ⇒ SV ngoài lớp "
        "nhận 404 TREE_NOT_PUBLISHED thay vì 403 NOT_ENROLLED"
    ),
    "test_du_phong.py::test_demo_bat_llm_sap_phien_van_chay_tron_va_judge_ap_br03": (
        "lỗi của Đăng (C1-13): app/ai/demo.py judge_result() đối chiếu từ khóa (MATCH_RATIO) không nhận diện "
        "đủ ý bắt buộc của rubric trong mẫu GOOD ⇒ REQUIRED_POINTS fail dù totalScore (78.35) ≥ passThreshold"
    ),
    "test_du_phong.py::test_het_ngan_sach_token_sv_bat_dau_lai_duoc": (
        "lỗi của Đăng (C1-07): hết ngân sách token (429 TOKEN_BUDGET_EXCEEDED) giữa phiên không gọi "
        "MasteryService.abandon như đường FLAGGED ⇒ ô mastery giữ IN_PROGRESS, SV không mở được phiên mới dù "
        "thông báo lỗi nói 'Hãy bắt đầu phiên mới' (SV có thể tự POST /sessions/{id}/abandon để gỡ, bug #189)"
    ),
    "test_vong2_db.py::test_cau_hinh_lop_doi_nguong_dat_va_so_cau_ap_vao_phien_moi": _CHO_CAU_HINH_GIO,
    "test_vong2_db.py::test_cau_phan_bien_co_han_tra_loi_theo_cau_hinh": _CHO_CAU_HINH_GIO,
    "test_vong2_db.py::test_het_gio_ghi_chua_tra_loi_va_sang_cau_ke": _CHO_CAU_HINH_GIO,
    "test_vong2_db.py::test_tra_loi_tre_qua_han_bi_tinh_het_gio_loi_tre_khong_vao_transcript": _CHO_CAU_HINH_GIO,
    "test_du_phong.py::test_may_chu_khoi_dong_lai_giua_phan_bien_khoi_phuc_du_phien": _CHO_CAU_HINH_GIO,
}


def pytest_itemcollected(item: pytest.Item) -> None:
    goc = item.nodeid.replace("\\", "/").split("tests/integration/")[-1]
    for ten, ly_do in _XFAIL_THEO_TEN.items():
        if goc == ten or goc.startswith(ten + "["):
            item.add_marker(pytest.mark.xfail(strict=True, reason=ly_do))
