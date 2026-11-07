"""KT-15 – Test vòng 3 trên Postgres thật: lịch sử phiên, nghe lại, xuất báo cáo (FR-TB-15, FR-HM-10; C2-20, GD-16).

"Xong khi" của thẻ: báo cáo xuất ra đúng số liệu của lớp. Lớp ở đây là LỚP MẪU `seed/` (30 SV, cây CTDL&GT 11 nút)
nạp bằng `scripts/seed_db.py`; GV mẫu phát hành cây qua API rồi ma trận được dựng theo một KỊCH BẢN cố định
(tổ tiên N5 luôn Đạt, N5 9 Đạt / 21 Chưa đạt như demo KT-05, các nút khác theo công thức bên dưới) – ghi qua
`MasteryService` như luồng thật. Đáp án so sánh lấy từ kịch bản + `seed/users.json` + bảng `mastery_records`, KHÔNG
lấy từ `HeatmapService` (nguồn của báo cáo), nên lỗi tổng hợp ở báo cáo sẽ bị bắt.
Chạy khi có TEST_DATABASE_URL (CI job backend đặt sẵn); không có thì bỏ qua.
"""

import csv
import importlib.util
import io
import json
import sys
from collections import Counter
from graphlib import TopologicalSorter
from pathlib import Path
from uuid import UUID

import pymupdf
import pytest
from sqlalchemy import select

from app.models.session import MasteryRecord, SessionTurn, TeachingSession
from app.models.users import ClassSection, User
from tests.integration.lop_vong import DB_URL, LOI_GIANG, TRA_LOI, LopVong
from tests.integration.test_bao_mat_phan_quyen_db import WEBM, NguoiDung

pytestmark = pytest.mark.skipif(not DB_URL, reason="đặt TEST_DATABASE_URL để chạy trên Postgres thật")

API = "/api/v1"
ROOT = Path(__file__).resolve().parents[3]
MAT_KHAU_SEED = "Whybi@2026"  # mật khẩu mẫu dev/demo trong seed/users.json
N5 = "n5_con_tro"
NHAN = {"MASTERED": "Đạt", "NOT_PASSED": "Chưa đạt", "AVAILABLE": "Sẵn sàng", "LOCKED": "Khóa"}
DAT = {"MASTERED", "NEEDS_REVERIFY"}


def _nap_script(name: str):
    spec = importlib.util.spec_from_file_location(f"kt15_{name}", ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class LopMau:
    """Lớp mẫu seed đã phát hành cây + kịch bản ma trận. `ke_hoach[email][key]` = MASTERED / NOT_PASSED (đã thử)."""

    def __init__(self, lop: LopVong):
        self.lop, self.db, self.api = lop, lop.db, lop.api
        seed = _nap_script("seed_db")
        bundle = seed.load_seed()
        seed.write_db(self.db, bundle)
        self.users = json.loads((ROOT / "seed/users.json").read_text(encoding="utf-8"))
        join = json.loads((ROOT / "seed/class.json").read_text(encoding="utf-8"))["class"]["join_code"]
        self.class_id = self.db.scalar(select(ClassSection.id).where(ClassSection.join_code == join))
        self.gv = self._nguoi(self.users["lecturers"][0])
        self.tree = self._phat_hanh()
        self.nodes = {n["key"]: n for n in self.tree["nodes"]}
        self.parents = {k: set() for k in self.nodes}
        for e in self.tree["edges"]:
            self.parents[e["toKey"]].add(e["fromKey"])
        self.order = list(TopologicalSorter(self.parents).static_order())
        self.ids = {
            sv["email"]: self.db.scalar(select(User.id).where(User.email == sv["email"]))
            for sv in self.users["students"]
        }
        self.ke_hoach = self._dung_ma_tran()

    def _nguoi(self, acc: dict) -> NguoiDung:
        u = self.db.scalar(select(User).where(User.email == acc["email"]))
        n = NguoiDung(u.id, u.email, u.full_name)
        n.headers = self.lop.dang_nhap(u.email, MAT_KHAU_SEED)
        return n

    def sv(self, i: int) -> NguoiDung:
        return self._nguoi(self.users["students"][i])

    def _phat_hanh(self) -> dict:
        """GV mẫu duyệt rubric (nút chưa có rubric dùng rubric N5 của seed) rồi phát hành – qua API, token thật."""
        h = self.gv.headers
        r = self.api.get(f"{API}/classes/{self.class_id}/tree", headers=h, params={"draft": "true"})
        assert r.status_code == 200, r.text
        tv = r.json()
        if tv["status"] == "PUBLISHED":
            return tv
        mau = next(n["rubric"] for n in tv["nodes"] if n.get("rubric"))
        for n in tv["nodes"]:
            rb = (n.get("rubric") or mau) | {"approved": True}
            r = self.api.put(f"{API}/nodes/{n['id']}/rubric", headers=h, json=rb)
            assert r.status_code == 200, r.text
        r = self.api.post(f"{API}/tree-versions/{tv['id']}/publish", headers=h)
        assert r.status_code == 200, r.text
        return r.json()

    def _to_tien(self, key: str) -> set[str]:
        out, stack = set(), list(self.parents[key])
        while stack:
            k = stack.pop()
            if k not in out:
                out.add(k)
                stack.extend(self.parents[k])
        return out

    def _dung_ma_tran(self) -> dict[str, dict[str, str]]:
        """Kịch bản: tổ tiên N5 luôn Đạt; N5: 9 SV đầu Đạt, 21 SV sau Chưa đạt; nút khác chỉ học khi đã mở khóa,
        bỏ qua khi (i + j) % 4 == 0, Đạt khi (7i + j) % 10 < 6. SV cuối (sv30) không học gì – hàng trống."""
        to_tien_n5 = self._to_tien(N5)
        plan: dict[str, dict[str, str]] = {}
        for i, acc in enumerate(self.users["students"]):
            mine: dict[str, str] = {}
            plan[acc["email"]] = mine
            if i == len(self.users["students"]) - 1:
                continue
            for j, key in enumerate(self.order):
                if any(mine.get(p) != "MASTERED" for p in self.parents[key]):
                    continue  # còn khóa
                if key in to_tien_n5:
                    passed = True
                elif key == N5:
                    passed = i < 9
                elif (i + j) % 4 == 0:
                    continue
                else:
                    passed = (7 * i + j) % 10 < 6
                self.lop.dat_nut(self.ids[acc["email"]], self.tree, key, passed=passed, class_id=self.class_id)
                mine[key] = "MASTERED" if passed else "NOT_PASSED"
        return plan

    # ------------------------------------------------------------------ đáp án độc lập với báo cáo

    def trang_thai_db(self) -> dict[tuple[UUID, str], str]:
        key_of = {UUID(n["id"]): k for k, n in self.nodes.items()}
        rows = self.db.scalars(select(MasteryRecord).where(MasteryRecord.class_id == self.class_id)).all()
        return {(r.student_id, key_of[r.node_id]): r.state for r in rows if r.node_id in key_of}

    def bao_cao(self, fmt: str = "csv", nguoi: NguoiDung | None = None):
        return self.api.get(
            f"{API}/classes/{self.class_id}/report", headers=(nguoi or self.gv).headers, params={"format": fmt}
        )


@pytest.fixture
def lop_mau(lop_vong: LopVong) -> LopMau:
    return LopMau(lop_vong)


def _doc_csv(r) -> tuple[list[str], dict[str, list[str]], dict[str, list[str]]]:
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    head = rows[0]
    students = {x[0]: x for x in rows[1:] if x and x[0]}
    footer = {x[1]: x for x in rows[1:] if x and not x[0] and len(x) > 1}
    return head, students, footer


# --- Báo cáo CSV đúng số liệu lớp mẫu ------------------------------------------------------------


def test_kich_ban_seed_dung_nhu_demo(lop_mau: LopMau):
    """Tiền đề: ma trận trong CSDL đúng kịch bản (30 SV seed, N5 9 Đạt / 21 Chưa đạt)."""
    assert len(lop_mau.users["students"]) == 30 and len(lop_mau.nodes) == 11
    db = lop_mau.trang_thai_db()
    for email, plan in lop_mau.ke_hoach.items():
        for key, state in plan.items():
            assert db[(lop_mau.ids[email], key)] == state, (email, key)
    n5 = Counter(p.get(N5) for p in lop_mau.ke_hoach.values())
    assert n5 == {"MASTERED": 9, "NOT_PASSED": 20, None: 1}


def test_csv_khop_tung_o_cua_ma_tran_lop_mau(lop_mau: LopMau):
    r = lop_mau.bao_cao("csv")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    cd = r.headers["content-disposition"]
    assert "attachment" in cd and ".csv" in cd and "ctdl" in cd.lower()
    head, students, _ = _doc_csv(r)
    codes = [lop_mau.nodes[k]["code"] for k in lop_mau.nodes]
    assert head[:4] == ["MSSV", "Họ tên", "Số nút Đạt", "Tiến độ (%)"] and sorted(head[4:]) == sorted(codes)
    col = {lop_mau.nodes[k]["code"]: k for k in lop_mau.nodes}

    # Đủ 30 SV của seed (cả SV chưa học gì), đúng MSSV + họ tên trong users.json
    assert set(students) == {s["student_code"] for s in lop_mau.users["students"]}
    db = lop_mau.trang_thai_db()
    for acc in lop_mau.users["students"]:
        row, plan = students[acc["student_code"]], lop_mau.ke_hoach[acc["email"]]
        assert row[1] == acc["full_name"]
        dat = sum(1 for s in plan.values() if s in DAT)
        assert int(row[2]) == dat, acc["email"]
        assert int(row[3]) == round(dat / len(lop_mau.nodes) * 100), acc["email"]
        for idx, code in enumerate(head[4:], start=4):
            key = col[code]
            if key in plan:
                assert row[idx] == NHAN[plan[key]], (acc["email"], code)
            else:
                # chưa thử: không được tính là Đạt / Chưa đạt; nhãn khớp ô trong CSDL (nếu có)
                assert row[idx] not in ("Đạt", "Chưa đạt"), (acc["email"], code)
                state = db.get((lop_mau.ids[acc["email"]], key))
                assert row[idx] == (NHAN.get(state, "") if state else ""), (acc["email"], code, state)


def test_csv_dong_tong_ket_theo_nut_khop_dem_doc_lap(lop_mau: LopMau):
    head, _, footer = _doc_csv(lop_mau.bao_cao("csv"))
    assert set(footer) >= {"Đã thử", "Đạt", "Tỉ lệ Đạt (%)"}
    col = {lop_mau.nodes[k]["code"]: k for k in lop_mau.nodes}
    for idx, code in enumerate(head[4:], start=4):
        key = col[code]
        states = [p[key] for p in lop_mau.ke_hoach.values() if key in p]
        thu, dat = len(states), sum(s in DAT for s in states)
        assert int(footer["Đã thử"][idx]) == thu, code
        assert int(footer["Đạt"][idx]) == dat, code
        assert footer["Tỉ lệ Đạt (%)"][idx] == (str(round(dat / thu * 100)) if thu else ""), code
    n5 = head.index(lop_mau.nodes[N5]["code"])
    assert (footer["Đã thử"][n5], footer["Đạt"][n5], footer["Tỉ lệ Đạt (%)"][n5]) == ("29", "9", "31")


def test_csv_khop_ban_do_nhiet_gv_dang_xem(lop_mau: LopMau):
    """GD-16: nút Xuất ở GV-05 – tệp phải cùng số với màn bản đồ nhiệt (FR-HM-10)."""
    snap = lop_mau.api.get(f"{API}/classes/{lop_mau.class_id}/heatmap", headers=lop_mau.gv.headers).json()
    head, students, footer = _doc_csv(lop_mau.bao_cao("csv"))
    assert snap["enrolledCount"] == len(students) == 30
    for n in snap["nodes"]:
        idx = head.index(n["code"])
        assert int(footer["Đã thử"][idx]) == n["attemptedCount"]
        assert int(footer["Đạt"][idx]) == n["passedCount"]
    for g in snap["grid"]:
        assert int(students[g["studentCode"]][2]) == g["masteredCount"]


# --- Báo cáo PDF -----------------------------------------------------------------------------------


def test_pdf_mo_duoc_va_dung_so_lieu_lop_mau(lop_mau: LopMau):
    r = lop_mau.bao_cao("pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf", r.text
    assert r.content.startswith(b"%PDF") and ".pdf" in r.headers["content-disposition"]
    text = "\n".join(p.get_text() for p in pymupdf.open("pdf", r.content))
    flat = " ".join(text.split())
    assert "CTDL&GT – Nhóm 02" in flat and "HK1 2026-2027" in flat
    assert "Sĩ số 30 sinh viên" in flat
    total = len(lop_mau.nodes)
    for key, node in lop_mau.nodes.items():
        states = [p[key] for p in lop_mau.ke_hoach.values() if key in p]
        assert f"{sum(s in DAT for s in states)}/{len(states)}" in flat, node["code"]
    for acc in lop_mau.users["students"]:
        dat = sum(1 for s in lop_mau.ke_hoach[acc["email"]].values() if s in DAT)
        assert acc["full_name"] in flat and f"{dat}/{total}" in flat, acc["email"]
    # N5: 9/29 = 31 % < 40 % ⇒ Đỏ, màu luôn kèm chữ; cảnh báo điểm nghẽn có trong báo cáo
    assert "Đỏ – điểm nghẽn" in flat
    snap = lop_mau.api.get(f"{API}/classes/{lop_mau.class_id}/heatmap", headers=lop_mau.gv.headers).json()
    assert snap["alerts"], "lớp mẫu có điểm nghẽn"
    for a in snap["alerts"]:
        assert " ".join(a["message"].split()) in flat


def test_bao_cao_cap_nhat_sau_phien_moi_va_chi_gv_phu_trach(lop_mau: LopMau):
    """Phiên thật (LLM_MODE=fake) của SV chưa học gì ⇒ báo cáo đổi đúng ô đó, các ô khác giữ nguyên."""
    sv30 = lop_mau.sv(29)
    acc = lop_mau.users["students"][29]
    _, truoc, foot_truoc = _doc_csv(lop_mau.bao_cao("csv"))
    goc = lop_mau.order[0]
    lop_mau.lop.giang_tron(sv30, lop_mau.tree, goc)
    state = lop_mau.trang_thai_db()[(sv30.id, goc)]
    assert state in ("MASTERED", "NOT_PASSED")
    head, sau, foot_sau = _doc_csv(lop_mau.bao_cao("csv"))
    idx = head.index(lop_mau.nodes[goc]["code"])
    assert sau[acc["student_code"]][idx] == NHAN[state]
    assert int(foot_sau["Đã thử"][idx]) == int(foot_truoc["Đã thử"][idx]) + 1
    assert int(foot_sau["Đạt"][idx]) == int(foot_truoc["Đạt"][idx]) + (state == "MASTERED")
    assert {k: v for k, v in sau.items() if k != acc["student_code"]} == {
        k: v for k, v in truoc.items() if k != acc["student_code"]
    }
    # Quyền: SV, GV khác lớp không tải được; định dạng lạ bị từ chối
    for nguoi in (sv30, lop_mau.lop.gv_a):
        assert lop_mau.bao_cao("csv", nguoi).status_code == 403
    assert lop_mau.bao_cao("xlsx").status_code == 422


# --- Lịch sử phiên + nghe lại (FR-TB-15) trên tài khoản seed ------------------------------------


def test_lich_su_phien_sv_seed_khop_csdl_va_ho_so_gv(lop_mau: LopMau):
    sv = lop_mau.sv(0)
    r = lop_mau.api.get(f"{API}/me/sessions", headers=sv.headers, params={"class_id": str(lop_mau.class_id)})
    assert r.status_code == 200, r.text
    ds = r.json()
    db_ids = set(
        lop_mau.db.scalars(
            select(TeachingSession.id).where(
                TeachingSession.student_id == sv.id, TeachingSession.class_id == lop_mau.class_id
            )
        )
    )
    assert {UUID(x["sessionId"]) for x in ds} == db_ids and len(ds) == len(lop_mau.ke_hoach[sv.email])
    ket_qua = {x["nodeId"]: x["verdict"] for x in ds}
    for key, state in lop_mau.ke_hoach[sv.email].items():
        assert ket_qua[lop_mau.nodes[key]["id"]] == ("PASSED" if state == "MASTERED" else "FAILED"), key
    # Hồ sơ SV ở GV-07 cùng danh sách phiên và cùng số nút Đạt
    p = lop_mau.api.get(f"{API}/classes/{lop_mau.class_id}/students/{sv.id}/profile", headers=lop_mau.gv.headers).json()
    assert {s["sessionId"] for s in p["sessions"]} == {x["sessionId"] for x in ds}
    assert p["masteredCount"] == sum(s in DAT for s in lop_mau.ke_hoach[sv.email].values())
    assert p["totalCount"] == len(lop_mau.nodes)


def test_phien_giong_noi_moi_nhat_truoc_nghe_lai_dung_ban_ghi(lop_mau: LopMau, kho_am_thanh):
    lop = lop_mau.lop
    sv = lop_mau.sv(29)  # SV chưa học gì ⇒ nút gốc đang mở
    goc = lop_mau.order[0]
    sid = lop.mo_phien(sv, lop_mau.tree, goc, inputMode="VOICE")["sessionId"]
    r = lop.api.post(
        f"{API}/sessions/{sid}/audio",
        headers=sv.headers,
        files={"file": ("loi-giang.webm", WEBM, "audio/webm")},
        data={"consent": "true"},
    )
    assert r.status_code == 200, r.text
    tr = r.json()
    r = lop.luot(
        sv, sid, LOI_GIANG, "EXPLANATION", inputMode="VOICE", audioRef=tr["audioRef"], sttConfidence=tr["confidence"]
    )
    assert r.status_code == 200, r.text
    reply = r.json()
    while reply["status"] == "CHALLENGING":
        reply = lop.luot(sv, sid, TRA_LOI).json()
    assert reply["status"] == "COMPLETED"
    kq = lop.ket_qua(sv, sid)

    ds = lop.api.get(f"{API}/me/sessions", headers=sv.headers).json()
    assert ds[0]["sessionId"] == sid, "phiên mới nhất đứng đầu"
    assert ds[0]["verdict"] == kq["verdict"] and ds[0]["totalScore"] == kq["totalScore"]

    ct = lop.api.get(f"{API}/me/sessions/{sid}", headers=sv.headers).json()
    assert ct["nodeKey"] == goc and ct["result"]["verdict"] == kq["verdict"]
    rows = lop_mau.db.scalars(
        select(SessionTurn).where(SessionTurn.session_id == UUID(sid)).order_by(SessionTurn.turn_no)
    ).all()
    assert [(t["turnNo"], t["speaker"], t["content"]) for t in ct["turns"]] == [
        (t.turn_no, t.speaker, t.content) for t in rows
    ]
    voice = [t for t in ct["turns"] if t["inputMode"] == "VOICE"]
    assert len(voice) == 1 and voice[0]["audioUrl"]
    nghe = lop.api.get(voice[0]["audioUrl"], headers=sv.headers)
    assert nghe.status_code == 200 and nghe.content == WEBM
    # GV phụ trách nghe cùng bản ghi từ hồ sơ; SV khác không xem / nghe được
    nghe_gv = lop.api.get(voice[0]["audioUrl"], headers=lop_mau.gv.headers)
    assert nghe_gv.status_code == 200 and nghe_gv.content == WEBM
    khac = lop_mau.sv(0)
    assert lop.api.get(f"{API}/me/sessions/{sid}", headers=khac.headers).status_code in (403, 404)
    assert lop.api.get(voice[0]["audioUrl"], headers=khac.headers).status_code == 403


# --- KT-14 trên lớp mẫu: tìm SV và chế độ trình chiếu ẩn tên (FR-HM-09, C2-17 / GD-14) ------------


def test_trinh_chieu_an_ten_va_tim_sv_khong_doi_so_lieu(lop_mau: LopMau):
    url, h = f"{API}/classes/{lop_mau.class_id}/heatmap", lop_mau.gv.headers
    thuong = lop_mau.api.get(url, headers=h).json()
    an = lop_mau.api.get(url, headers=h, params={"anonymize": "true"})
    assert an.status_code == 200, an.text
    for acc in lop_mau.users["students"]:
        assert acc["full_name"] not in an.text and acc["student_code"] not in an.text, acc["email"]
        assert acc["email"] not in an.text
    body = an.json()
    assert body["nodes"] == thuong["nodes"] and body["enrolledCount"] == thuong["enrolledCount"]
    assert sorted(g["masteredCount"] for g in body["grid"]) == sorted(g["masteredCount"] for g in thuong["grid"])
    # chi tiết nút khi chiếu cũng không lộ tên
    d = lop_mau.api.get(
        f"{API}/classes/{lop_mau.class_id}/nodes/{lop_mau.nodes[N5]['id']}/detail",
        headers=h,
        params={"anonymize": "true"},
    )
    assert d.status_code == 200 and not any(a["full_name"] in d.text for a in lop_mau.users["students"])
    # tìm theo MSSV / tên (không phân biệt hoa thường)
    acc = lop_mau.users["students"][4]
    for q in (acc["student_code"], acc["full_name"].upper()):
        grid = lop_mau.api.get(url, headers=h, params={"q": q}).json()["grid"]
        assert [g["studentCode"] for g in grid] == [acc["student_code"]], q
    assert lop_mau.api.get(url, headers=h, params={"q": "khong-co-ai"}).json()["grid"] == []
