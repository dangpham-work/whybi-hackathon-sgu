"""C2-17 – Xong khi: đổi ngưỡng thì màu đổi theo. Cấu hình lớp (FR-HM-08), lọc / ẩn tên (FR-HM-09)."""

import pytest
from sqlalchemy import select

from app.models.enums import MasteryState
from app.models.users import ClassSection
from tests.unit import test_rootcause_db as _c212
from tests.unit.test_tree_edit_db import DB_URL

world = _c212.world
lop30 = _c212.lop30
vi_du_6_9 = _c212.vi_du_6_9
N6 = _c212.N6

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

DEFAULT = {"passThreshold": 70, "greenThreshold": 0.7, "yellowThreshold": 0.4, "minSample": 5, "challengeCount": 3}


def url(w, suffix=""):
    return f"/api/v1/classes/{w.class_id}{suffix}"


def _n6(w):
    return next(n for n in w.api.get(url(w, "/heatmap")).json()["nodes"] if n["nodeKey"] == N6)


def test_get_settings_mac_dinh(lop30):
    w, *_ = lop30
    assert w.api.get(url(w, "/settings")).json() == DEFAULT


def test_doi_nguong_thi_mau_doi_theo(vi_du_6_9):
    """N6: 3/12 Đạt = 25 % ⇒ ĐỎ. Hạ ngưỡng vàng xuống 20 % ⇒ VÀNG, cả ảnh chụp lẫn class_node_stats."""
    w, ids, _ = vi_du_6_9
    assert _n6(w)["color"] == "RED"
    r = w.api.put(url(w, "/settings"), json=DEFAULT | {"yellowThreshold": 0.2})
    assert r.status_code == 200, r.text
    assert r.json()["yellowThreshold"] == 0.2
    assert _n6(w)["color"] == "YELLOW"
    from tests.unit.test_heatmap_db import stats

    assert stats(w, ids)[N6].color == "YELLOW"


def test_doi_co_mau_toi_thieu_thi_xam(vi_du_6_9):
    w, *_ = vi_du_6_9
    w.api.put(url(w, "/settings"), json=DEFAULT | {"minSample": 13})  # N6 mới có 12 SV thử
    n6 = _n6(w)
    assert n6["color"] == "GREY" and n6["sample"] == "INSUFFICIENT"


def test_luu_nguong_dat_va_so_cau_phan_bien(lop30):
    w, *_ = lop30
    r = w.api.put(url(w, "/settings"), json=DEFAULT | {"passThreshold": 80, "challengeCount": 5})
    assert r.status_code == 200
    cls = w.db.scalar(select(ClassSection).where(ClassSection.id == w.class_id))
    assert (cls.pass_threshold, cls.challenge_count) == (80, 5)
    assert w.api.get(url(w, "/settings")).json()["challengeCount"] == 5


@pytest.mark.parametrize(
    "patch",
    [
        {"yellowThreshold": 0.8},  # vàng phải thấp hơn xanh
        {"greenThreshold": 1.2},
        {"yellowThreshold": 0},
        {"passThreshold": 101},
        {"minSample": 0},
        {"challengeCount": 2},  # FR-TB-08: 3–5 câu
        {"challengeCount": 6},
    ],
)
def test_cau_hinh_sai_422(lop30, patch):
    w, *_ = lop30
    assert w.api.put(url(w, "/settings"), json=DEFAULT | patch).status_code == 422


@pytest.mark.parametrize("who", ["gv_other", "sv"])
def test_chi_gv_phu_trach_sua_cau_hinh(lop30, who):
    w, *_ = lop30
    w.current = getattr(w, who)
    assert w.api.put(url(w, "/settings"), json=DEFAULT).status_code == 403
    assert w.api.get(url(w, "/settings")).status_code == 403


def test_loc_theo_ten_va_mssv(lop30):
    w, *_ = lop30
    full = w.api.get(url(w, "/heatmap")).json()["grid"]
    assert len(full) == 30
    r = w.api.get(url(w, "/heatmap"), params={"q": "sv 1"}).json()
    names = [g["studentName"] for g in r["grid"]]
    assert names and all("sv 1" in n.lower() for n in names) and len(names) < 30
    code = full[0]["studentCode"]
    assert [g["studentCode"] for g in w.api.get(url(w, "/heatmap"), params={"q": code}).json()["grid"]] == [code]


def test_che_do_trinh_chieu_an_ten(vi_du_6_9):
    w, ids, truot = vi_du_6_9
    body = w.api.get(url(w, "/heatmap"), params={"anonymize": "true"}).json()
    assert all(g["studentCode"] == "" and g["studentName"].startswith("SV ") for g in body["grid"])
    assert len({g["studentName"] for g in body["grid"]}) == 30  # vẫn phân biệt được từng hàng
    detail = w.api.get(url(w, f"/nodes/{ids[N6]}/detail"), params={"anonymize": "true"}).json()
    names = [s["studentName"] for grp in detail["studentsByState"].values() for s in grp]
    assert names and all(n.startswith("SV ") for n in names)
    assert body["nodes"]  # số liệu nút không đổi
    assert MasteryState.NOT_PASSED.value in detail["studentsByState"]
