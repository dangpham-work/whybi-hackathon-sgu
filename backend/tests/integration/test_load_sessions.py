"""KT-13: phần tính toán của script kiểm thử tải (phân vị, tỉ lệ lỗi, biểu đồ hộp).

Không cần stack – chỉ kiểm hàm thuần trong `evals/perf/load_sessions.py`.
"""

import importlib.util
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def load():
    spec = importlib.util.spec_from_file_location("load_sessions", ROOT / "evals" / "perf" / "load_sessions.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["load_sessions"] = module
    spec.loader.exec_module(module)
    return module


def req(load, ms, status=200, endpoint="POST /sessions", error=None):
    return load.RequestRecord(endpoint=endpoint, status=status, latency_ms=ms, error=error)


# ------------------------------------------------------------------ phân vị


def test_phan_vi_noi_suy_tuyen_tinh(load):
    # Cùng quy ước numpy "linear": vị trí (n-1)·p
    values = [10, 20, 30, 40]
    assert load.percentile(values, 50) == pytest.approx(25)
    assert load.percentile(values, 95) == pytest.approx(38.5)
    assert load.percentile(values, 0) == 10
    assert load.percentile(values, 100) == 40


def test_phan_vi_khong_phu_thuoc_thu_tu_va_mot_phan_tu(load):
    assert load.percentile([40, 10, 30, 20], 50) == pytest.approx(25)
    assert load.percentile([7], 95) == 7


def test_phan_vi_rong_hoac_ngoai_mien_bao_loi(load):
    with pytest.raises(ValueError):
        load.percentile([], 50)
    with pytest.raises(ValueError):
        load.percentile([1, 2], 101)


# ------------------------------------------------------------------ tỉ lệ lỗi


def test_loi_gom_http_4xx_5xx_va_loi_ket_noi(load):
    assert not req(load, 5, 201).failed
    assert req(load, 5, 409).failed
    assert req(load, 5, 503).failed
    assert req(load, 5, 0, error="ReadTimeout").failed


def test_tom_tat_muc_tai(load):
    ok = load.SessionRecord(
        index=0,
        completed=True,
        duration_ms=300,
        turns=3,
        requests=[req(load, 100, endpoint="POST /auth/login"), req(load, 100), req(load, 100)],
    )
    bad = load.SessionRecord(
        index=1,
        completed=False,
        duration_ms=150,
        turns=0,
        requests=[req(load, 100), req(load, 50, 500, "POST /sessions")],
        error="POST /sessions: HTTP 500",
    )
    s = load.summarize(2, [ok, bad], wall_ms=320)
    assert s["sessions"] == 2
    assert s["requests"] == 5
    assert s["requestErrors"] == 1
    assert s["requestErrorRate"] == pytest.approx(0.2)
    assert s["sessionErrors"] == 1
    assert s["sessionErrorRate"] == pytest.approx(0.5)
    assert s["latencyMs"]["p50"] == pytest.approx(100)
    assert s["latencyMs"]["max"] == 100  # độ trễ chỉ tính request thành công
    assert s["latencyNoLoginMs"]["count"] == 3  # bỏ đăng nhập (Argon2) để thấy riêng luồng phiên
    assert s["sessionMs"]["p50"] == pytest.approx(300)  # chỉ phiên hoàn tất
    assert s["throughputRps"] == pytest.approx(5 / 0.32)
    assert s["errorsByKind"] == {"POST /sessions: HTTP 500": 1}
    assert s["byEndpoint"]["POST /sessions"]["count"] == 4
    assert s["byEndpoint"]["POST /sessions"]["errors"] == 1
    assert s["byEndpoint"]["POST /auth/login"]["count"] == 1


def test_tom_tat_khi_moi_request_deu_loi(load):
    bad = load.SessionRecord(
        index=0, completed=False, duration_ms=10, turns=0, requests=[req(load, 10, 0, error="ConnectError")], error="x"
    )
    s = load.summarize(1, [bad], wall_ms=10)
    assert s["requestErrorRate"] == 1
    assert s["latencyMs"] is None
    assert s["sessionMs"] is None


# ------------------------------------------------------------------ biểu đồ hộp


def test_thong_so_hop_va_diem_ngoai_lai(load):
    b = load.box_stats([1, 2, 3, 4, 5, 6, 7, 8, 9, 100])
    assert b["median"] == pytest.approx(5.5)
    assert b["q1"] == pytest.approx(3.25)
    assert b["q3"] == pytest.approx(7.75)
    assert b["whiskerHigh"] == 9  # 100 > q3 + 1,5·IQR
    assert b["whiskerLow"] == 1
    assert b["outliers"] == [100]


def test_svg_hop_lop_va_ty_le_loi_hop_le(load):
    levels = {
        20: {"values": [10, 20, 30, 40, 50], "requestErrorRate": 0.0, "sessionErrorRate": 0.0},
        100: {"values": [15, 25, 35, 400], "requestErrorRate": 0.125, "sessionErrorRate": 0.5},
    }
    svg = load.render_svg(levels, title="Độ trễ")
    root = ET.fromstring(svg)  # XML hợp lệ
    assert root.tag.endswith("svg")
    text = "".join(root.itertext())
    assert "20 phiên" in text and "100 phiên" in text
    assert "12,5 %" in text  # tỉ lệ lỗi ghi bằng chữ, không chỉ bằng màu
    assert "Độ trễ" in text
