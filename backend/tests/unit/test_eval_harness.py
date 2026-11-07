"""C1-16 / C1-17 – khung đo: Cohen's κ, ma trận nhầm lẫn, tỉ lệ lộ đáp án; bộ judge / tutee chạy được với LLM giả."""

import importlib.util
import sys
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parents[3] / "evals"
sys.path.insert(0, str(EVALS))

import metrics  # noqa: E402


@pytest.fixture(scope="module")
def run_mod():
    spec = importlib.util.spec_from_file_location("evals_run", EVALS / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_kappa_hoan_hao_ngau_nhien_va_nguoc():
    t = ["P", "P", "F", "F"]
    assert metrics.cohen_kappa(t, t) == 1.0
    assert metrics.cohen_kappa(t, ["P", "F", "P", "F"]) == 0.0
    assert metrics.cohen_kappa(t, ["F", "F", "P", "P"]) == -1.0


def test_kappa_ket_qua_da_biet():
    # 20 mẫu: 10 P / 10 F; Judge đoán đúng 8 P và 7 F ⇒ po = 0,75, pe = 0,5 ⇒ κ = 0,5
    truth = ["P"] * 10 + ["F"] * 10
    pred = ["P"] * 8 + ["F"] * 2 + ["F"] * 7 + ["P"] * 3
    assert metrics.cohen_kappa(truth, pred) == pytest.approx(0.5)


def test_kappa_mot_nhan_duy_nhat_khong_chia_cho_0():
    assert metrics.cohen_kappa(["P", "P"], ["P", "P"]) == 1.0
    assert metrics.cohen_kappa(["P", "P"], ["F", "F"]) == 0.0
    with pytest.raises(ValueError):
        metrics.cohen_kappa([], [])


def test_ma_tran_nham_lan_va_bang_markdown():
    m = metrics.confusion(["P", "P", "F"], ["P", "F", "F"], ["P", "F"])
    assert m == {"P": {"P": 1, "F": 1}, "F": {"P": 0, "F": 1}}
    assert metrics.format_confusion(m).splitlines()[2] == "| P | 1 | 1 |"
    with pytest.raises(ValueError):
        metrics.confusion(["P"], [], ["P"])


def test_ti_le_va_sai_so():
    assert metrics.rate(1, 20) == 0.05 and metrics.rate(3, 0) == 0.0
    assert metrics.mean_abs_error([10, 20], [20, 10]) == 10
    assert metrics.accuracy(["P", "F"], ["P", "P"]) == 0.5


def test_bo_judge_chay_duoc_voi_llm_gia_va_khong_ghi_ket_qua(run_mod, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["run.py", "judge", "--runs=1"])
    before = (EVALS / "results" / "judge.md").read_text(encoding="utf-8")
    run_mod.run_judge()
    out = capsys.readouterr().out
    assert "κ =" in out and "KHÔNG ghi results/" in out and "nháp AI" in out
    assert (EVALS / "results" / "judge.md").read_text(encoding="utf-8") == before


def test_bo_tutee_dem_cau_lo_va_vi_pham_vai(run_mod, monkeypatch, capsys):
    from eval_datasets import TuteeSession

    leak = "Con trỏ là biến lưu địa chỉ của một ô nhớ, đúng không?"  # lặp lại ý chính + xác nhận
    clean = "Mình thắc mắc: nếu hai biến cùng trỏ tới một chỗ thì sao nhỉ?"
    sessions = [
        TuteeSession.model_validate(
            {
                "id": "T01",
                "node": "N5",
                "turns": [
                    {"role": "student", "text": "Con trỏ lưu địa chỉ."},
                    {"role": "tutee", "text": leak},
                    {"role": "student", "text": "Ừ."},
                    {"role": "tutee", "text": clean},
                ],
                "leak_annotations": [1],
            }
        )
    ]
    monkeypatch.setattr(run_mod.datasets, "load_tutee", lambda: sessions)
    monkeypatch.setattr(sys, "argv", ["run.py", "tutee"])
    run_mod.run_tutee()
    out = capsys.readouterr().out
    assert "1/2 = 50.0%" in out and "Guard bắt 1/1" in out and "chặn nhầm 0/1" in out
