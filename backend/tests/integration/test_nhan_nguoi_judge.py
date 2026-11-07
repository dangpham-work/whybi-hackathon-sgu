"""Công cụ gán nhãn người cho Judge: xuất phiếu mù, đọc phiếu, đo κ giữa 2 người, gộp nhãn chốt."""

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load():
    path = ROOT / "evals" / "judge" / "nhan_nguoi.py"
    spec = importlib.util.spec_from_file_location("nhan_nguoi", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["nhan_nguoi"] = module
    spec.loader.exec_module(module)
    return module


nn = _load()

COT_DIEM = ["CORRECTNESS", "COVERAGE", "ESSENCE", "ROBUSTNESS", "CLARITY"]


def _mau(id_, label="PASSED"):
    return {
        "id": id_,
        "node": "N1",
        "transcript": f"lời giảng {id_}",
        "label": label,
        "scores": dict.fromkeys(COT_DIEM, 70),
        "annotator": "Quyền (nháp AI)",
        "source": "ai_draft",
        "covered_points": ["KP1"],
    }


def _cay():
    return {
        "nodes": [
            {
                "code": "N1",
                "title": "Biến",
                "rubric": {"keyPoints": [{"id": "KP1", "content": "Biến là vùng nhớ", "isRequired": True}]},
            }
        ]
    }


def _viet_phieu(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=nn.COT_PHIEU)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in nn.COT_PHIEU})
    return path


def _dong(id_, nhan, diem=70):
    return {"id": id_, "nhan": nhan, **{c: diem for c in COT_DIEM}}


def test_xuat_phieu_khong_lo_nhan_cu_va_xao_tron_theo_nguoi(tmp_path):
    mau = [_mau(f"J{i:03d}", "PASSED" if i % 2 else "FAILED") for i in range(1, 21)]
    a = nn.xuat_phieu(mau, _cay(), "Quyền", tmp_path)
    b = nn.xuat_phieu(mau, _cay(), "Thắng", tmp_path)

    noi_dung = a.read_text(encoding="utf-8-sig")
    assert "PASSED" not in noi_dung and "FAILED" not in noi_dung and "nháp AI" not in noi_dung
    with a.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 20
    assert rows[0]["y_bat_buoc"].startswith("KP1: Biến là vùng nhớ")
    assert all(r["nhan"] == "" and r["CORRECTNESS"] == "" for r in rows)
    with b.open(encoding="utf-8-sig") as f:
        thu_tu_b = [r["id"] for r in csv.DictReader(f)]
    assert [r["id"] for r in rows] != thu_tu_b  # mỗi người một thứ tự
    assert sorted(thu_tu_b) == sorted(r["id"] for r in rows)


def test_doc_phieu_chap_nhan_chu_viet_va_bao_dung_dong_sai(tmp_path):
    ok = _viet_phieu(tmp_path / "ok.csv", [_dong("J001", "Đạt"), _dong("J002", "chưa đạt")])
    assert {k: v["label"] for k, v in nn.doc_phieu(ok).items()} == {"J001": "PASSED", "J002": "FAILED"}

    sai_nhan = _viet_phieu(tmp_path / "sai.csv", [_dong("J001", "Đạt"), _dong("J002", "có lẽ")])
    with pytest.raises(ValueError, match=r"sai\.csv:3"):
        nn.doc_phieu(sai_nhan)

    sai_diem = _viet_phieu(tmp_path / "diem.csv", [_dong("J001", "Đạt", diem=150)])
    with pytest.raises(ValueError, match=r"diem\.csv:2.*0–100"):
        nn.doc_phieu(sai_diem)

    thieu = _viet_phieu(tmp_path / "thieu.csv", [{"id": "J001", "nhan": ""}])
    with pytest.raises(ValueError, match=r"thieu\.csv:2"):
        nn.doc_phieu(thieu)


def test_doi_chieu_tinh_kappa_va_liet_ke_tranh_chap(tmp_path):
    a = nn.doc_phieu(
        _viet_phieu(tmp_path / "a.csv", [_dong("J001", "Đạt"), _dong("J002", "Chưa đạt"), _dong("J003", "Đạt")])
    )
    b = nn.doc_phieu(
        _viet_phieu(tmp_path / "b.csv", [_dong("J001", "Đạt"), _dong("J002", "Chưa đạt"), _dong("J003", "Chưa đạt")])
    )
    kappa, tranh_chap = nn.doi_chieu(a, b)
    assert tranh_chap == ["J003"]
    assert kappa == pytest.approx(0.4)


def test_doi_chieu_bao_loi_khi_hai_phieu_khac_tap_id(tmp_path):
    a = nn.doc_phieu(_viet_phieu(tmp_path / "a.csv", [_dong("J001", "Đạt")]))
    b = nn.doc_phieu(_viet_phieu(tmp_path / "b.csv", [_dong("J002", "Đạt")]))
    with pytest.raises(ValueError, match="J001"):
        nn.doi_chieu(a, b)


def test_gop_can_nhan_chot_cho_moi_tranh_chap():
    mau = [_mau("J001"), _mau("J002")]
    a = {
        "J001": {"label": "PASSED", "scores": dict.fromkeys(COT_DIEM, 80)},
        "J002": {"label": "PASSED", "scores": dict.fromkeys(COT_DIEM, 60)},
    }
    b = {
        "J001": {"label": "PASSED", "scores": dict.fromkeys(COT_DIEM, 70)},
        "J002": {"label": "FAILED", "scores": dict.fromkeys(COT_DIEM, 40)},
    }

    with pytest.raises(ValueError, match="J002"):
        nn.gop(mau, a, b, "Quyền", "Thắng", chot={})

    ket_qua = nn.gop(mau, a, b, "Quyền", "Thắng", chot={"J002": "FAILED"})
    j1, j2 = ket_qua
    assert j1["label"] == "PASSED" and j1["scores"]["CORRECTNESS"] == 75  # trung bình 2 người
    assert j2["label"] == "FAILED"
    assert all(j["source"] == "human" and j["annotator"] == "Quyền & Thắng" for j in ket_qua)
    assert "covered_points" not in j1  # ý đã nêu do AI soạn → bỏ, không gán cho người
    assert j1["transcript"] == "lời giảng J001" and j1["node"] == "N1"
    assert "tranh chấp" in j2["note"]


def test_gop_ra_dung_schema_bo_danh_gia():
    sys.path.insert(0, str(ROOT / "evals"))
    import eval_datasets as ds  # noqa: PLC0415

    mau = [_mau("J001")]
    a = {"J001": {"label": "PASSED", "scores": dict.fromkeys(COT_DIEM, 80)}}
    b = {"J001": {"label": "PASSED", "scores": dict.fromkeys(COT_DIEM, 75)}}
    for j in nn.gop(mau, a, b, "Quyền", "Thắng", chot={}):
        ds.LabeledExplanation.model_validate(j)  # điểm trung bình 77,5 phải làm tròn thành số nguyên
        json.dumps(j, ensure_ascii=False)
