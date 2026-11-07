"""KT-09: P/R/F1 cây với ánh xạ một-một; không cần DB hoặc LLM."""

import copy
import importlib.util
import json
import os
import subprocess
import sys
import unicodedata
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.schemas.tree import Edge, Node, TreeVersion

ROOT = Path(__file__).resolve().parents[3]


def _load_tree_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


datasets = _load_tree_module("kt09_datasets", ROOT / "evals/eval_datasets.py")
tree_metrics = _load_tree_module("kt09_metrics", ROOT / "evals/tree/metrics.py")


def _tree(nodes, edges=()):
    return TreeVersion(
        nodes=[Node(key=key, title=title) for key, title in nodes],
        edges=[Edge(from_key=source, to_key=target) for source, target in edges],
    )


def _gold(nodes, edges=(), aliases=None, name="sample"):
    return datasets.GoldTree(name=name, subject="Mẫu", syllabus=None, tree=_tree(nodes, edges), aliases=aliases or {})


def _counts(tp, fp, fn):
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
    }


def test_metrics_normalizes_unicode_case_and_whitespace_without_removing_meaning():
    assert tree_metrics.normalize_title("  CON\tTRỎ \n") == "con trỏ"
    assert tree_metrics.normalize_title(unicodedata.normalize("NFD", "Con trỏ")) == "con trỏ"
    assert tree_metrics.normalize_title("Ｃ＋＋") == "c++"
    assert tree_metrics.normalize_title("Con tro") != tree_metrics.normalize_title("Con trỏ")
    assert tree_metrics.normalize_title("C++") != tree_metrics.normalize_title("C")
    assert tree_metrics.normalize_title("malloc/free") != tree_metrics.normalize_title("malloc free")


@pytest.mark.parametrize("value", ["", " \t\n", None, 42])
def test_metrics_rejects_empty_or_nontext_titles(value):
    with pytest.raises(ValueError, match="title"):
        tree_metrics.normalize_title(value)


def test_metrics_matches_aliases_and_different_ids_without_using_keys():
    gold = _gold([("a", "Con trỏ"), ("b", "Mảng")], [("a", "b")], {"a": ["Pointer"]})
    pred = _tree([("p", "pointer"), ("q", " MẢNG ")], [("p", "q")])
    score = tree_metrics.evaluate_tree(pred, gold)
    assert score["mapping"] == {"p": "a", "q": "b"}
    assert score["nodes"] == _counts(2, 0, 0)
    assert score["edges"] == _counts(1, 0, 0)
    assert tree_metrics.evaluate_tree(_tree([("a", "Sai khái niệm")]), gold)["nodes"] == _counts(0, 1, 2)


@pytest.mark.parametrize("aliases", [{"a": ["B"]}, {"a": ["same"], "b": [" SAME "]}])
def test_metrics_rejects_ambiguous_gold_aliases(aliases):
    gold = _gold([("a", "A"), ("b", "B")], aliases=aliases)
    with pytest.raises(ValueError, match="ambiguous"):
        tree_metrics.evaluate_tree(_tree([]), gold)


@pytest.mark.parametrize("aliases", [{"unknown": ["A"]}, {"a": [" "]}, {"a": "Alias"}])
def test_metrics_rejects_invalid_gold_aliases(aliases):
    with pytest.raises(ValueError):
        tree_metrics.evaluate_tree(_tree([]), _gold([("a", "A")], aliases=aliases))


def test_metrics_duplicate_predictions_count_as_fp_with_stable_representative():
    gold = _gold([("a", "Con trỏ"), ("b", "Mảng")], [("a", "b")], {"a": ["Pointer"]})
    nodes = [("z", "Con trỏ"), ("a", "Pointer"), ("m", "Con trỏ"), ("b", "Mảng")]
    edges = [("a", "b"), ("z", "b")]
    score = tree_metrics.evaluate_tree(_tree(nodes, edges), gold)
    assert score == tree_metrics.evaluate_tree(_tree(list(reversed(nodes)), list(reversed(edges))), gold)
    assert score["mapping"] == {"m": "a", "b": "b"}
    assert score["nodes"] == _counts(2, 2, 0)
    assert score["edges"] == _counts(0, 2, 1)  # Không chọn nút có cạnh để tăng điểm.
    assert score["duplicate_matches"] == [
        {"gold_key": "a", "kept_predicted_key": "m", "extra_predicted_keys": ["a", "z"]}
    ]


def test_metrics_reversed_and_unmatched_endpoint_edges_remain_false_positives():
    gold = _gold([("a", "A"), ("b", "B"), ("c", "C")], [("a", "b"), ("b", "c")])
    pred = _tree([("x", "A"), ("y", "B"), ("z", "D")], [("y", "x"), ("y", "z")])
    score = tree_metrics.evaluate_tree(pred, gold)
    assert score["nodes"] == _counts(2, 1, 1)
    assert score["edges"] == _counts(0, 2, 2)
    assert score["unmatched_predicted_nodes"] == ["z"]
    assert score["unmatched_gold_nodes"] == ["c"]
    assert score["false_positive_edges"] == [["y", "x"], ["y", "z"]]
    assert score["false_negative_edges"] == [["a", "b"], ["b", "c"]]


def test_metrics_does_not_silently_remove_transitive_edges():
    nodes = [("a", "A"), ("b", "B"), ("c", "C")]
    gold = _gold(nodes, [("a", "b"), ("b", "c")])
    pred = _tree(nodes, [("a", "b"), ("b", "c"), ("a", "c")])
    assert tree_metrics.evaluate_tree(pred, gold)["edges"] == _counts(2, 1, 0)


@pytest.mark.parametrize("side", ["pred", "gold"])
@pytest.mark.parametrize("bad_edges", [[("a", "b"), ("a", "b")], [("a", "b"), ("b", "a")]])
def test_metrics_rejects_duplicate_edges_and_cycles(side, bad_edges):
    gold = _gold([("a", "A"), ("b", "B")])
    pred = _tree([("a", "A"), ("b", "B")])
    (pred if side == "pred" else gold.tree).edges = [Edge(from_key=a, to_key=b) for a, b in bad_edges]
    with pytest.raises(ValueError, match="duplicate edge|cycle"):
        tree_metrics.evaluate_tree(pred, gold)


@pytest.mark.parametrize("bad", ["key", "unknown", "self", "blank"])
def test_metrics_validates_models_even_if_mutated_after_construction(bad):
    pred = _tree([("a", "A"), ("b", "B")])
    if bad == "key":
        pred.nodes[1].key = "a"
    elif bad == "unknown":
        pred.edges.append(Edge(from_key="a", to_key="unknown"))
    elif bad == "self":
        pred.edges.append(Edge(from_key="a", to_key="a"))
    else:
        pred.nodes[0].title = " "
    with pytest.raises(ValueError):
        tree_metrics.evaluate_tree(pred, _gold([("a", "A")]))


def test_metrics_empty_predictions_are_failures_and_empty_denominators_are_not_perfect():
    gold = _gold([("a", "A"), ("b", "B")], [("a", "b")])
    score = tree_metrics.evaluate_tree(_tree([]), gold)
    assert score["nodes"] == _counts(0, 0, 2)
    assert score["edges"] == _counts(0, 0, 1)
    both_empty = tree_metrics.evaluate_tree(_tree([]), _gold([]))
    assert both_empty["nodes"] == both_empty["edges"] == _counts(0, 0, 0)
    assert tree_metrics.evaluate_tree(_tree([("a", "A")]), _gold([]))["nodes"] == _counts(0, 1, 0)


def test_metrics_micro_and_macro_keep_distinct_case_weights_and_defined_counts():
    small = tree_metrics.evaluate_tree(_tree([("a", "A")]), _gold([("a", "A")], name="small"))
    large = tree_metrics.evaluate_tree(_tree([]), _gold([(f"n{i}", f"N{i}") for i in range(9)], name="large"))
    got = tree_metrics.aggregate([small, large])
    assert got["cases"] == 2
    assert got["nodes"]["micro"] == _counts(1, 0, 9)
    assert got["nodes"]["macro"] == {
        "precision": 1.0,
        "recall": 0.5,
        "f1": 0.5,
        "defined": {"precision": 1, "recall": 2, "f1": 2},
    }
    assert got["edges"]["macro"] == {
        "precision": None,
        "recall": None,
        "f1": None,
        "defined": {"precision": 0, "recall": 0, "f1": 0},
    }
    assert tree_metrics.aggregate([])["nodes"]["micro"] == _counts(0, 0, 0)


@pytest.mark.parametrize("bad_count", [-1, 0.5, True, "1"])
def test_metrics_aggregate_rejects_invalid_counts(bad_count):
    score = tree_metrics.evaluate_tree(_tree([]), _gold([]))
    score["nodes"]["tp"] = bad_count
    with pytest.raises(ValueError, match="count"):
        tree_metrics.aggregate([score])


def test_metrics_aggregate_recomputes_ratios_from_counts_instead_of_trusting_artifact():
    score = tree_metrics.evaluate_tree(_tree([]), _gold([("a", "A")]))
    score["nodes"]["f1"] = 1.0
    result = tree_metrics.aggregate([score])
    assert result["nodes"]["micro"]["f1"] == result["nodes"]["macro"]["f1"] == 0.0


@pytest.fixture
def tree_runner():
    path = ROOT / "evals/tree/evaluate.py"
    spec = importlib.util.spec_from_file_location("kt09_tree_evaluate", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fake_tree_run(tree_runner):
    from app.ai.gateway import LLMGateway
    from app.ai.providers.fake import FakeProvider

    cases = [c for c in tree_runner.load_cases() if c.gold.name == "ctdl_gt"]
    ticks = iter([10.0, 11.0, 14.0, 16.0])
    with_gateway = LLMGateway(FakeProvider(), cache_size=0)
    try:
        return tree_runner.collect(cases, with_gateway, mode="fake", clock=lambda: next(ticks))
    finally:
        with_gateway.close()


def test_runner_fake_do_tung_cong_doan_va_giu_nhan_pending(tree_runner, fake_tree_run):
    case = fake_tree_run["cases"][0]
    assert case["error"] is None and case["page_count"] == 1
    assert case["timings"] == {"extract_seconds": 1.0, "build_seconds": 3.0, "sanitize_seconds": 2.0}
    assert case["syllabus_sha256"] and case["gold_sha256"]
    assert case["gold"]["_source"] and case["prediction"]["nodes"]
    assert tree_runner.summarize(fake_tree_run)["status"] == "SIMULATION"
    assert tree_runner.summarize(fake_tree_run)["edge_target_met"] is None
    review = tree_runner.draft_review(fake_tree_run)
    assert review["source"] == "pending" and review["cases"][0]["approved"] is None


def test_runner_khong_bo_qua_case_thieu_giao_trinh(tree_runner):
    gateway = SimpleNamespace(primary=SimpleNamespace(name="fake"), fallback=None)
    cases = [c for c in tree_runner.load_cases() if c.gold.syllabus is None]
    assert len(cases) == 2
    run = tree_runner.collect(cases, gateway, mode="fake")
    assert len(run["cases"]) == 2
    assert all(c["error"] == "MISSING_SYLLABUS" for c in run["cases"])
    result = tree_runner.summarize(run)
    assert result["processed_all"] is False and result["scored_cases"] == 0
    assert result["benchmark_complete"] is False


def test_runner_chan_demo_va_fake_gan_nhan_real(tree_runner, monkeypatch):
    from app.core.config import get_settings

    cases = tree_runner.load_cases()[:1]
    fake = SimpleNamespace(name="fake")
    for gateway in (
        SimpleNamespace(primary=fake, fallback=None),
        SimpleNamespace(primary=SimpleNamespace(name="gemini"), fallback=fake),
    ):
        with pytest.raises(ValueError, match="fake"):
            tree_runner.collect(cases, gateway, mode="real")
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    with pytest.raises(ValueError, match="DEMO_MODE"):
        tree_runner.collect(cases, SimpleNamespace(primary=fake, fallback=None), mode="fake")


def _reviewed_three_case_run(tree_runner, fake_tree_run):
    run = copy.deepcopy(fake_tree_run)
    run["mode"] = "real"
    run["gateway_config"] = [{"provider": "gemini", "model": "unit-test-only"}]
    run["gateway_calls"] = []
    original = run["cases"][0]
    original["prediction"] = original["gold"]
    run["cases"] = [copy.deepcopy(original) for _ in range(3)]
    for i, case in enumerate(run["cases"]):
        case["name"] = f"fixture_{i}"
        case["syllabus_sha256"] = tree_runner.sha256(f"unit-test-only-source-{i}".encode())
        run["gateway_calls"].append(
            {"case": case["name"], "provider": "gemini", "model": "unit-test-only", "outcome": "ok"}
        )
    review = tree_runner.draft_review(run)
    review.update(source="human", reviewer="Unit test fixture, not empirical evidence")
    for case in review["cases"]:
        case["approved"] = True
    return run, review


@pytest.mark.parametrize(
    "defect",
    [
        "duplicate_source",
        "missing_hash",
        "missing_call",
        "error_call",
        "wrong_case",
        "no_config",
        "timing",
        "empty_gold",
    ],
)
def test_runner_khong_cong_nhan_bo_do_thieu_bang_chung(tree_runner, fake_tree_run, defect):
    run, _ = _reviewed_three_case_run(tree_runner, fake_tree_run)
    if defect == "duplicate_source":
        run["cases"][1]["syllabus_sha256"] = run["cases"][0]["syllabus_sha256"]
    elif defect == "missing_hash":
        run["cases"][0]["syllabus_sha256"] = None
    elif defect == "missing_call":
        run["gateway_calls"].pop()
    elif defect == "error_call":
        run["gateway_calls"][0]["outcome"] = "invalid_output"
    elif defect == "wrong_case":
        run["gateway_calls"][0]["case"] = "not_in_run"
    elif defect == "no_config":
        run["gateway_config"] = []
    elif defect == "timing":
        run["cases"][0]["timings"] = {}
    else:
        run["cases"][0]["gold"]["edges"] = []
    result = tree_runner.summarize(run)
    assert result["status"] == "INCOMPLETE"
    assert result["benchmark_complete"] is False
    assert result["edge_target_met"] is None


def test_runner_chan_cau_hinh_fake_trong_bang_chung_real(tree_runner, fake_tree_run):
    run, _ = _reviewed_three_case_run(tree_runner, fake_tree_run)
    run["gateway_config"].append({"provider": "fake", "model": "fake"})
    with pytest.raises(ValueError, match="fake"):
        tree_runner.summarize(run)


def test_runner_khong_goi_thoi_gian_trich_cay_la_nghiem_thu_mt1(tree_runner, fake_tree_run):
    run, review = _reviewed_three_case_run(tree_runner, fake_tree_run)
    result = tree_runner.summarize(run, review)
    assert result["edge_target_met"] is True
    assert result["status"] == "PARTIAL_SCOPE"
    assert result["pipeline_seconds"] is None
    assert tree_runner.summarize(run)["status"] == "NEEDS_REVIEW"
    run["cases"][0]["error"] = "LLM_UNAVAILABLE"
    assert tree_runner.summarize(run)["status"] == "INCOMPLETE"


@pytest.mark.parametrize("defect", ["run", "source_hash", "duplicate", "string_flag", "reviewer"])
def test_runner_tu_choi_review_sai_luot_hoac_nhan(tree_runner, fake_tree_run, defect):
    run, review = _reviewed_three_case_run(tree_runner, fake_tree_run)
    if defect == "run":
        run["cases"][0]["page_count"] = 99
    elif defect == "source_hash":
        review["cases"][0]["syllabus_sha256"] = "wrong"
    elif defect == "duplicate":
        review["cases"].append(copy.deepcopy(review["cases"][0]))
    elif defect == "string_flag":
        review["cases"][0]["approved"] = "true"
    else:
        review["reviewer"] = None
    with pytest.raises(ValueError):
        tree_runner.summarize(run, review)


def test_runner_tinh_lai_scores_va_chan_trace_fake_trong_real(tree_runner, fake_tree_run):
    run = copy.deepcopy(fake_tree_run)
    run["cases"][0]["scores"] = {"edges": {"f1": 1.0}}
    assert tree_runner.summarize(run)["aggregate"]["edges"]["micro"]["f1"] == 0
    run["mode"] = "real"
    with pytest.raises(ValueError, match="fake"):
        tree_runner.summarize(run)


def test_runner_giu_bang_chung_va_khong_ghi_bao_cao_chinh_thuc(tree_runner, fake_tree_run, tmp_path):
    official = ROOT / "evals/results/tree.md"
    before = official.read_bytes()
    output = tmp_path / "artifacts"
    tree_runner.write_outputs(fake_tree_run, output)
    snapshot = (output / "run.json").read_bytes()
    with pytest.raises(FileExistsError):
        tree_runner.write_outputs(fake_tree_run, output)
    assert (output / "run.json").read_bytes() == snapshot and official.read_bytes() == before


def test_runner_cli_fake_utf8_va_missing_cases(tmp_path):
    env = dict(os.environ, APP_ENV="test", LLM_MODE="fake", DEMO_MODE="0", PYTHONIOENCODING="ascii")
    for select, expected_code in ((["--case", "ctdl_gt"], 0), ([], 1)):
        output = tmp_path / ("one" if select else "all")
        result = subprocess.run(
            [sys.executable, str(ROOT / "evals/tree/evaluate.py"), "collect", "--output", str(output), *select],
            cwd=ROOT / "backend",
            env=env,
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == expected_code, result.stderr.decode("utf-8", errors="replace")
        assert "SIMULATION" in result.stdout.decode("utf-8")
        run = json.loads((output / "run.json").read_text(encoding="utf-8"))
        assert len(run["cases"]) == (1 if select else 3)
        assert all(call["provider"] == "fake" for call in run["gateway_calls"])
