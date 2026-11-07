"""evals/cost.py – đo chi phí AI mỗi phiên (tiêu chí VI): luồng phiên chạy đủ bước, tính tiền và báo cáo đúng."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load():
    spec = importlib.util.spec_from_file_location("cost_eval", ROOT / "evals" / "cost.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["cost_eval"] = module
    spec.loader.exec_module(module)
    return module


cost = _load()


def test_chi_phi_theo_bang_gia():
    # gpt-4o-mini: 0,15 $/1M vào, 0,60 $/1M ra
    assert cost.chi_phi("gpt-4o-mini", 1_000_000, 0) == pytest.approx(0.15)
    assert cost.chi_phi("gpt-4o-mini", 10_000, 2_000) == pytest.approx(0.0015 + 0.0012)


def test_luong_phien_goi_du_cac_buoc_qua_gateway():
    """LLM giả: mỗi phiên phải đi qua Tutee mở đầu, bao phủ, câu hỏi, Judge – và đếm được từng lời gọi."""
    from app.ai.gateway import reset_gateway

    try:
        phien = cost.do_cau_hinh("gemini", "gpt-4o-mini", 1)
    finally:
        reset_gateway()
    assert len(phien) == 1 and not phien[0].loi
    buoc = {g.schema for g in phien[0].goi}
    assert {"TuteeUtterance", "CoverageAnalysis", "JudgeResult"} <= buoc


def test_bao_cao_hien_phien_loi_va_ty_trong():
    goi = [cost.LoiGoi("JudgeResult", "gpt-4o-mini", 3000, 1000, 900, "ok")]
    ok = cost.Phien("T01", goi=goi, giay=10)
    hong = cost.Phien("T02", loi="AppError: hết ngân sách")
    md = cost.bao_cao({"gpt-4o-mini": [ok, hong]})
    assert "| `gpt-4o-mini` | 1/2 |" in md
    assert "100%" in md  # một bước duy nhất chiếm toàn bộ chi phí
    assert "T02: AppError: hết ngân sách" in md
