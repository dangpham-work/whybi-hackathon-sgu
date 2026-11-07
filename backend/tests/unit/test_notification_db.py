"""C2-19 – Xong khi: gợi ý ghép cặp mới tạo thông báo trong ứng dụng và email (FR-AD-08, Bảng 5.11)."""

import pytest

from app.models.users import Notification
from app.services import notification as notif
from app.services.notification import NotificationService
from tests.unit.test_matching_db import bus, k, two_way, world  # noqa: F401
from tests.unit.test_tree_edit_db import DB_URL

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

API = "/api/v1"


@pytest.fixture
def sent(monkeypatch):
    """Ghi lại những gì được đẩy lên WebSocket và email thay vì gửi thật."""
    pushed: list[tuple[str, str, dict]] = []
    emails: list[tuple[str, str, str]] = []
    monkeypatch.setattr(notif, "broadcast", lambda ch, ev, payload: pushed.append((ch, ev, payload)))
    monkeypatch.setattr(notif, "email_sender", lambda to, subject, body: emails.append((to, subject, body)))
    return pushed, emails


def test_goi_y_ghep_cap_tao_thong_bao_ung_dung_va_email(k, sent):  # noqa: F811
    pushed, emails = sent
    k.run_round()
    k.db.expire_all()
    rows = k.db.query(Notification).filter(Notification.type == "MATCH_PROPOSED").all()
    receivers = {n.user_id for n in rows}
    assert {k.ids["An"], k.ids["Chau"], k.ids["Ha"], k.ids["Dung"]} <= receivers
    assert all(n.link == f"/sv/classes/{k.w.class_id}/peers" and not n.is_read for n in rows)
    # WebSocket: mỗi người nhận đúng một sự kiện trên kênh user:{id}
    chans = {ch for ch, ev, _ in pushed if ev == "notification"}
    assert {f"user:{k.ids[n]}" for n in ("An", "Chau", "Ha", "Dung")} <= chans
    assert len(emails) == len(rows) and all(s.startswith("[Whybi AI]") for _, s, _ in emails)


def test_khong_giao_khi_giao_dich_bi_rollback(world, sent):  # noqa: F811
    pushed, emails = sent
    with pytest.raises(RuntimeError):
        try:
            NotificationService(world.db).notify(world.sv, "X", "Không được giao", email=True)
            raise RuntimeError("lỗi giữa chừng")
        except RuntimeError:
            world.db.rollback()
            raise
    assert pushed == [] and emails == []


def test_giao_sau_khi_commit(world, sent):  # noqa: F811
    pushed, emails = sent
    NotificationService(world.db).notify(world.sv, "T", "Chào", "nội dung", "/x", email=True)
    assert pushed == [] and emails == [], "chưa commit thì chưa giao"
    world.db.commit()
    assert [(ch, ev, p.title) for ch, ev, p in pushed] == [(f"user:{world.sv}", "notification", "Chào")]
    assert len(emails) == 1 and emails[0][0].endswith("@whybi.test") and "nội dung" in emails[0][2]


def test_ca_hai_chap_nhan_gui_thong_tin_lien_he(k, sent):  # noqa: F811
    pushed, emails = sent
    mid = two_way(k)
    k.act("An", mid, "accept")
    k.act("Chau", mid, "accept")
    k.db.expire_all()
    rows = k.db.query(Notification).filter(Notification.type == "MATCH_ACCEPTED").all()
    assert {n.user_id for n in rows} == {k.ids["An"], k.ids["Chau"]}
    assert all("@" in n.content for n in rows), "có email liên hệ của bạn học"
    assert sum(1 for _, s, _ in emails if "xác nhận" in s) == 2


def test_api_danh_sach_doc_va_chi_cua_minh(k, sent):  # noqa: F811
    k.run_round()
    api = k.as_("An")
    mine = api.get(f"{API}/notifications").json()
    assert len(mine) >= 1 and all(n["type"].startswith("MATCH_") for n in mine)
    first = mine[0]
    assert first["isRead"] is False and first["title"] and first["createdAt"]
    assert api.get(f"{API}/notifications", params={"unread_only": "true"}).json() == mine

    assert api.post(f"{API}/notifications/{first['id']}/read").json()["isRead"] is True
    assert all(n["id"] != first["id"] for n in api.get(f"{API}/notifications", params={"unread_only": "true"}).json())

    other = k.as_("Chau")
    assert other.post(f"{API}/notifications/{first['id']}/read").status_code == 404, "không đọc hộ người khác"
    assert api.post(f"{API}/notifications/read-all").json()["updated"] >= 0
    assert api.get(f"{API}/notifications", params={"unread_only": "true"}).json() == []
