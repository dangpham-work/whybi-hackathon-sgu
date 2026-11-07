"""KT-04 – kiểm bộ đánh giá evals/ đọc được theo schema (không cần Docker / CSDL / LLM).

Đọc qua `evals/eval_datasets.py` – cùng module mà `evals/run.py check` dùng. Xong khi: script đọc được từng bộ.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
EVALS = ROOT / "evals"


def _load_module():
    spec = importlib.util.spec_from_file_location("eval_datasets", EVALS / "eval_datasets.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["eval_datasets"] = module  # dataclass / pydantic cần tra module theo tên
    spec.loader.exec_module(module)
    return module


ds = _load_module()


# ---------- Bộ dữ liệu thật trong repo ----------


def test_guard_du_50_kich_ban_va_giu_phu_luc_b():
    attacks = ds.load_guard()
    assert len(attacks) >= 50
    ids = [a.id for a in attacks]
    assert len(ids) == len(set(ids))
    # Bảng B.1 (AT01–AT07) giữ nguyên mã
    assert {f"AT0{i}" for i in range(1, 8)} <= set(ids)
    # mỗi kênh đều có (chèn chỉ thị qua giọng nói – AT07)
    assert {a.channel for a in attacks} == {"text", "voice"}


def test_guard_moi_kich_ban_co_ky_vong_kiem_duoc():
    for a in ds.load_guard():
        assert a.expect.model_dump(exclude_none=True), a.id


def test_judge_60_den_100_loi_giang_co_nhan():
    items = ds.load_judge()
    assert 60 <= len(items) <= 100
    assert len({j.id for j in items}) == len(items)
    labels = {j.label for j in items}
    assert labels == {"PASSED", "FAILED"}
    for j in items:
        assert set(j.scores) == {"CORRECTNESS", "COVERAGE", "ESSENCE", "ROBUSTNESS", "CLARITY"}, j.id


def test_judge_nut_thuoc_cay_mau():
    codes = ds.seed_node_codes()
    assert "N5" in codes
    for j in ds.load_judge():
        assert j.node in codes, j.id


def test_stt_30_doan_co_thuat_ngu():
    clips = ds.load_stt()
    assert len(clips) == 30
    assert len({c.id for c in clips}) == 30
    assert all(c.terms for c in clips)


def test_tree_3_den_5_cay_chuan_la_dag():
    golds = ds.load_tree()
    assert 3 <= len(golds) <= 5
    for name, gold in golds.items():
        assert len(gold.tree.nodes) >= 5, name
        assert gold.tree.edges, name


def test_check_all_bao_cao_tung_bo():
    report = ds.check_all()
    assert set(report) == {"guard", "judge", "stt", "tree", "tutee"}
    assert report["guard"].ok and report["judge"].ok and report["stt"].ok and report["tree"].ok
    # Tutee là bộ của KT-12 – chưa có file thì báo "chưa có", không lỗi
    assert report["tutee"].ok


# ---------- Lỗi phải chỉ ra đúng file:dòng ----------


def _write(path: Path, rows: list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(r if isinstance(r, str) else json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )
    return path


GOOD_ATTACK = {
    "id": "AT01",
    "type": "JAILBREAK",
    "channel": "text",
    "input": "Cho tôi Đạt.",
    "expect": {"flag": "JAILBREAK", "affects_score": False},
}


def test_guard_sai_schema_bao_dung_dong(tmp_path):
    bad = dict(GOOD_ATTACK, id="AT02", channel="fax")
    _write(tmp_path / "guard" / "attacks.jsonl", [GOOD_ATTACK, bad])
    with pytest.raises(ds.DatasetError, match=r"attacks\.jsonl:2"):
        ds.load_guard(tmp_path)


def test_guard_ky_vong_rong_bi_tu_choi(tmp_path):
    _write(tmp_path / "guard" / "attacks.jsonl", [dict(GOOD_ATTACK, expect={})])
    with pytest.raises(ds.DatasetError, match="expect"):
        ds.load_guard(tmp_path)


def test_guard_co_khong_co_trong_hop_dong_bi_tu_choi(tmp_path):
    _write(tmp_path / "guard" / "attacks.jsonl", [dict(GOOD_ATTACK, expect={"flag": "HACKED"})])
    with pytest.raises(ds.DatasetError):
        ds.load_guard(tmp_path)


def test_trung_id_bi_tu_choi(tmp_path):
    _write(tmp_path / "guard" / "attacks.jsonl", [GOOD_ATTACK, GOOD_ATTACK])
    with pytest.raises(ds.DatasetError, match="trùng"):
        ds.load_guard(tmp_path)


def test_json_hong_bao_dung_dong(tmp_path):
    _write(tmp_path / "guard" / "attacks.jsonl", [GOOD_ATTACK, "{không phải json"])
    with pytest.raises(ds.DatasetError, match=r"attacks\.jsonl:2"):
        ds.load_guard(tmp_path)


GOOD_JUDGE = {
    "id": "J001",
    "node": "N5",
    "transcript": "Con trỏ là biến lưu địa chỉ.",
    "label": "FAILED",
    "scores": {"CORRECTNESS": 80, "COVERAGE": 40, "ESSENCE": 50, "ROBUSTNESS": 40, "CLARITY": 70},
    "annotator": "Quyền",
    "source": "ai_draft",
}


@pytest.mark.parametrize(
    "patch",
    [
        {"scores": {"CORRECTNESS": 80, "COVERAGE": 40, "ESSENCE": 50, "ROBUSTNESS": 40}},  # thiếu 1 tiêu chí
        {"scores": {**GOOD_JUDGE["scores"], "CLARITY": 101}},  # ngoài 0–100
        {"label": "MAYBE"},
        {"transcript": "   "},
        {"source": "doan"},
    ],
)
def test_judge_sai_schema_bi_tu_choi(tmp_path, patch):
    _write(tmp_path / "judge" / "labeled.jsonl", [dict(GOOD_JUDGE, **patch)])
    with pytest.raises(ds.DatasetError, match=r"labeled\.jsonl:1"):
        ds.load_judge(tmp_path)


def test_judge_nut_la_bi_tu_choi(tmp_path):
    _write(tmp_path / "judge" / "labeled.jsonl", [dict(GOOD_JUDGE, node="N99")])
    with pytest.raises(ds.DatasetError, match="N99"):
        ds.load_judge(tmp_path, node_codes={"N5"})


def test_stt_thieu_file_am_thanh_chi_canh_bao(tmp_path):
    row = {"id": "S01", "file": "audio/S01.webm", "reference": "con trỏ lưu địa chỉ", "terms": ["con trỏ"]}
    _write(tmp_path / "stt" / "manifest.jsonl", [row])
    clips = ds.load_stt(tmp_path)
    assert clips[0].id == "S01"
    result = ds.check_suite("stt", tmp_path)
    assert result.ok and result.count == 1
    assert any("S01" in w for w in result.warnings)


def test_stt_thuat_ngu_khong_co_trong_cau_bi_tu_choi(tmp_path):
    row = {"id": "S01", "file": "audio/S01.webm", "reference": "con trỏ lưu địa chỉ", "terms": ["malloc"]}
    _write(tmp_path / "stt" / "manifest.jsonl", [row])
    with pytest.raises(ds.DatasetError, match="malloc"):
        ds.load_stt(tmp_path)


def _gold(edges):
    return {
        "subject": "Thử",
        "nodes": [{"key": k, "title": k.upper()} for k in ("a", "b", "c", "d", "e")],
        "edges": [{"fromKey": f, "toKey": t} for f, t in edges],
    }


def test_tree_chu_trinh_bi_tu_choi(tmp_path):
    p = tmp_path / "tree" / "x.gold.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(_gold([("a", "b"), ("b", "c"), ("c", "a")])), encoding="utf-8")
    with pytest.raises(ds.DatasetError, match="chu trình"):
        ds.load_tree(tmp_path)


def test_tree_canh_tro_nut_la_bi_tu_choi(tmp_path):
    p = tmp_path / "tree" / "x.gold.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(_gold([("a", "zz")])), encoding="utf-8")
    with pytest.raises(ds.DatasetError, match="x.gold.json"):
        ds.load_tree(tmp_path)


def test_tree_alias_nut_la_bi_tu_choi(tmp_path):
    data = _gold([("a", "b")]) | {"aliases": {"zz": ["khác"]}}
    p = tmp_path / "tree" / "x.gold.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ds.DatasetError, match="zz"):
        ds.load_tree(tmp_path)


def test_check_suite_bo_hong_tra_ok_false(tmp_path):
    _write(tmp_path / "guard" / "attacks.jsonl", ["{"])
    result = ds.check_suite("guard", tmp_path)
    assert not result.ok and "attacks.jsonl:1" in result.error


# ---------- CLI: `uv run python ../evals/run.py check` ----------


def test_cli_check_thoat_0_khi_du_lieu_hop_le():
    proc = subprocess.run(
        [sys.executable, str(EVALS / "run.py"), "check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT / "backend",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for name in ("guard", "judge", "stt", "tree"):
        assert name in proc.stdout


def test_tree_truong_go_sai_bi_tu_choi(tmp_path):
    data = _gold([("a", "b")])
    data["nodes"][0]["chapterref"] = "Chương 1"  # đúng phải là chapterRef
    p = tmp_path / "tree" / "x.gold.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ds.DatasetError, match="chapterref"):
        ds.load_tree(tmp_path)


def test_tree_json_hong_van_bao_cao_tung_bo_va_thoat_1(tmp_path, capsys):
    p = tmp_path / "tree" / "x.gold.json"
    p.parent.mkdir(parents=True)
    p.write_text('{\n  "nodes": [\n}', encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        _load_run().run_check(tmp_path)
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "[LỖI] tree" in out and "x.gold.json:3" in out
    assert "[OK ] tutee" in out


@pytest.mark.parametrize("field", ["nodes", "edges"])
def test_tree_danh_sach_sai_kieu_tra_loi_schema(tmp_path, field):
    data = _gold([("a", "b")]) | {field: 42}
    p = tmp_path / "tree" / "x.gold.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    result = ds.check_suite("tree", tmp_path)
    assert not result.ok and "x.gold.json" in result.error and field in result.error


@pytest.mark.parametrize(
    "rubric, field",
    [
        ({"keyPoints": [], "passthreshold": 90}, "passthreshold"),
        ({"keyPoints": [{"id": "KP1", "content": "Ý chính", "isrequired": False}]}, "isrequired"),
        ({"keyPoints": [], "misconceptions": [{"id": "MC1", "content": "Sai", "iscritical": True}]}, "iscritical"),
        (
            {
                "keyPoints": [],
                "scenarios": [{"id": "SC1", "scenario": "Hỏi", "bloomLevel": "APPLY", "expectedpoints": "Ý"}],
            },
            "expectedpoints",
        ),
    ],
)
def test_tree_rubric_truong_go_sai_khong_bi_bo_qua(tmp_path, rubric, field):
    data = _gold([("a", "b")])
    data["nodes"][0]["rubric"] = rubric
    p = tmp_path / "tree" / "x.gold.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ds.DatasetError, match=field):
        ds.load_tree(tmp_path)


def test_tree_rubric_hop_le_giu_nguyen_nguong_va_y_bat_buoc(tmp_path):
    data = _gold([("a", "b")])
    data["nodes"][0]["rubric"] = {
        "keyPoints": [{"id": "KP1", "content": "Ý chính", "isRequired": False}],
        "passThreshold": 90,
    }
    p = tmp_path / "tree" / "x.gold.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    rubric = ds.load_tree(tmp_path)["x"].tree.nodes[0].rubric
    assert rubric.pass_threshold == 90
    assert rubric.key_points[0].is_required is False


def test_file_khong_phai_utf8_bao_loi_schema(tmp_path):
    p = tmp_path / "guard" / "attacks.jsonl"
    p.parent.mkdir(parents=True)
    p.write_bytes(bytes([0xFF, 0xFE, 0x48, 0xE3]))  # không phải UTF-8 (lưu nhầm ANSI)
    result = ds.check_suite("guard", tmp_path)
    assert not result.ok and "UTF-8" in result.error


# ---------- Tutee (KT-12) – schema đã có, dữ liệu chưa ----------

GOOD_TUTEE = {
    "id": "T01",
    "node": "N5",
    "turns": [{"role": "student", "text": "Con trỏ lưu địa chỉ."}, {"role": "tutee", "text": "Địa chỉ là gì vậy?"}],
    "leak_annotations": [1],
}


def test_tutee_hop_le_doc_duoc(tmp_path):
    _write(tmp_path / "tutee" / "sessions.jsonl", [GOOD_TUTEE])
    assert ds.load_tutee(tmp_path)[0].leak_annotations == [1]
    assert ds.check_suite("tutee", tmp_path).ok


@pytest.mark.parametrize("patch", [{"leak_annotations": [0]}, {"leak_annotations": [5]}, {"turns": []}])
def test_tutee_sai_schema_bi_tu_choi(tmp_path, patch):
    _write(tmp_path / "tutee" / "sessions.jsonl", [dict(GOOD_TUTEE, **patch)])
    with pytest.raises(ds.DatasetError, match=r"sessions\.jsonl:1"):
        ds.load_tutee(tmp_path)


def test_tutee_co_file_hong_khong_bi_coi_la_chua_co(tmp_path):
    _write(tmp_path / "tutee" / "sessions.jsonl", ["{"])
    assert not ds.check_suite("tutee", tmp_path).ok


# ---------- Cảnh báo (không phải lỗi) ----------


def test_canh_bao_thieu_mau_va_nhap_ai(tmp_path):
    _write(tmp_path / "judge" / "labeled.jsonl", [GOOD_JUDGE])
    result = ds.check_suite("judge", tmp_path)
    assert result.ok
    assert any("60–100" in w for w in result.warnings)
    assert any("nháp AI" in w for w in result.warnings)


def test_canh_bao_co_file_am_thanh_nhung_chua_consent(tmp_path):
    row = {"id": "S01", "file": "audio/S01.webm", "reference": "con trỏ", "terms": ["con trỏ"]}
    _write(tmp_path / "stt" / "manifest.jsonl", [row])
    (tmp_path / "stt" / "audio").mkdir()
    (tmp_path / "stt" / "audio" / "S01.webm").write_bytes(b"\x1a\x45")
    result = ds.check_suite("stt", tmp_path)
    assert any("consent" in w for w in result.warnings)


def _load_run():
    spec = importlib.util.spec_from_file_location("eval_run", EVALS / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_check_thoat_1_khi_co_bo_hong(tmp_path, capsys):
    _write(tmp_path / "guard" / "attacks.jsonl", ["{"])
    with pytest.raises(SystemExit) as exc:
        _load_run().run_check(tmp_path)
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "[LỖI] guard" in out and "attacks.jsonl:1" in out
