"""KT-09: đo trích cây + DAG, giữ bằng chứng và chờ GV xác nhận cặp giáo trình/cây chuẩn.

Chạy từ backend: uv run python ../evals/tree/evaluate.py --help.
Không đo HTTP/queue/RAG/rubric; không dùng thời gian này kết luận MT1 toàn pipeline.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
import math
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evals"))

import eval_datasets as datasets  # noqa: E402

from app.ai.agents.tree_builder import TreeBuilder  # noqa: E402
from app.algorithms.dag import build_graph, sanitize  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.models.schemas.tree import TreeVersion  # noqa: E402
from app.services.syllabus import validate_syllabus  # noqa: E402
from app.workers.documents import ExtractionError, OcrError, TesseractOcr, extract_docx, extract_pdf  # noqa: E402

# Không import nhầm evals/metrics.py (bộ Judge/Tutee) khi pytest đã nạp module tên metrics.
_spec = importlib.util.spec_from_file_location("kt09_tree_metrics", Path(__file__).with_name("metrics.py"))
metrics = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = metrics
_spec.loader.exec_module(metrics)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(value) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8"))


@dataclass
class EvaluationCase:
    gold: datasets.GoldTree
    gold_data: dict
    gold_sha256: str
    source: Path | None


def load_cases(root: Path = ROOT / "evals") -> list[EvaluationCase]:
    cases = []
    for name, gold in datasets.load_tree(root).items():
        raw = (root / "tree" / f"{name}.gold.json").read_bytes()
        data = json.loads(raw)
        # Alias mơ hồ/cạnh trùng phải bị từ chối trước mọi lời gọi LLM.
        metrics.evaluate_tree(TreeVersion(nodes=[], edges=[]), gold)
        source = Path(gold.syllabus) if gold.syllabus else None
        if source is not None and not source.is_absolute():
            source = ROOT / source
        cases.append(EvaluationCase(gold, data, sha256(raw), source))
    return cases


class CallLog(logging.Handler):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.case = None

    def emit(self, record):
        if getattr(record, "event", None) == "llm.call":
            self.calls.append(
                {
                    "case": self.case,
                    **{
                        key: getattr(record, key, None)
                        for key in ("provider", "model", "outcome", "attempt", "input_tokens", "output_tokens")
                    },
                }
            )


def provenance() -> dict:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=5).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True, timeout=5))
    except (OSError, subprocess.SubprocessError):
        commit, dirty = None, None
    paths = [
        Path(__file__),
        Path(__file__).with_name("metrics.py"),
        ROOT / "backend/app/ai/agents/tree_builder.py",
        ROOT / "backend/app/algorithms/dag.py",
        ROOT / "backend/app/workers/documents.py",
        ROOT / "backend/app/ai/gateway.py",
        *sorted((ROOT / "backend/app/ai/prompts").glob("tree_*.md")),
    ]
    return {
        "commit": commit,
        "dirty": dirty,
        "file_hashes": {str(p.relative_to(ROOT)): sha256(p.read_bytes()) for p in paths},
    }


def collect(cases, gateway, *, mode: str, clock=time.perf_counter) -> dict:
    from app.core.config import get_settings

    if get_settings().demo_mode:
        raise ValueError("Cần DEMO_MODE=0, không dùng cây demo để đo")
    if mode not in {"fake", "real"} or not cases:
        raise ValueError("Cần mode fake/real và ít nhất một cặp dữ liệu")
    providers = [getattr(gateway, attr, None) for attr in ("primary", "fallback")]
    if mode == "real" and any(getattr(p, "name", None) == "fake" for p in providers):
        raise ValueError("Lượt real không được dùng primary/fallback fake")
    if mode == "fake" and getattr(providers[0], "name", None) != "fake":
        raise ValueError("Lượt fake cần gateway fake để tránh gọi model thật ngoài ý muốn")
    if len({c.gold.name for c in cases}) != len(cases):
        raise ValueError("Trùng mã cặp dữ liệu")
    run = {
        "schema_version": 1,
        "run_id": str(uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        "mode": mode,
        "scope": "extract_build_sanitize",
        "provenance": provenance(),
        "gateway_config": [
            {"provider": getattr(p, "name", None), "model": getattr(p, "model", None)}
            for p in providers
            if p is not None
        ],
        "cases": [],
    }
    trace = CallLog()
    logger = logging.getLogger("app.ai.gateway")
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(trace)
    try:
        for case in cases:
            trace.case = case.gold.name
            row = {
                "name": case.gold.name,
                "gold": case.gold_data,
                "gold_sha256": case.gold_sha256,
                "syllabus": str(case.source) if case.source else None,
                "syllabus_sha256": None,
                "page_count": None,
                "ocr_pages": [],
                "timings": {},
                "removed_edges": [],
                "prediction": None,
                "scores": None,
                "error": None,
            }
            run["cases"].append(row)
            if case.source is None or not case.source.is_file():
                row["error"] = "MISSING_SYLLABUS"
                continue
            try:
                data = case.source.read_bytes()
                row["syllabus_sha256"] = sha256(data)
                kind = validate_syllabus(case.source.name, data)
                started = clock()
                pages = extract_pdf(data, TesseractOcr()) if kind == "pdf" else extract_docx(data)
                extracted = clock()
                row["page_count"] = len(pages)
                row["ocr_pages"] = [p.number for p in pages if p.ocr]
                row["timings"]["extract_seconds"] = extracted - started
                raw = TreeBuilder(gateway).build([asdict(p) for p in pages])
                built = clock()
                row["timings"]["build_seconds"] = built - extracted
                dag, _, removed = sanitize(build_graph(raw))
                prediction = raw.model_copy(
                    update={"edges": [e for e in raw.edges if dag.has_edge(e.from_key, e.to_key)]}
                )
                row["timings"]["sanitize_seconds"] = clock() - built
                row["removed_edges"] = [list(edge) for edge in removed]
                row["prediction"] = prediction.model_dump(by_alias=True, mode="json")
                row["scores"] = metrics.evaluate_tree(prediction, case.gold)
            except AppError as exc:
                row["error"] = exc.code  # không lưu lỗi thô/khóa từ nhà cung cấp
            except OcrError:
                row["error"] = "OCR_UNAVAILABLE"
            except ExtractionError:
                row["error"] = "EXTRACTION_FAILED"
            except OSError:
                row["error"] = "SOURCE_READ_FAILED"
            except ValueError:
                row["error"] = "INVALID_TREE"
    finally:
        logger.removeHandler(trace)
        logger.setLevel(previous_level)
    run["gateway_calls"] = trace.calls
    return run


def _rows(run):
    if not isinstance(run, dict) or run.get("schema_version") != 1 or run.get("mode") not in {"fake", "real"}:
        raise ValueError("Run sai schema hoặc mode")
    if run.get("scope") != "extract_build_sanitize":
        raise ValueError("Run không đúng phạm vi bộ đo")
    rows = run["cases"]
    if not isinstance(rows, list) or not rows or len({c["name"] for c in rows}) != len(rows):
        raise ValueError("Cặp dữ liệu rỗng hoặc trùng tên")
    for row in rows:
        for seconds in row["timings"].values():
            if type(seconds) not in {int, float} or not math.isfinite(seconds) or seconds < 0:
                raise ValueError("Thời gian phải là số hữu hạn không âm")
    if run["mode"] == "real" and any(
        c.get("provider") == "fake" for c in run.get("gateway_calls", []) + run.get("gateway_config", [])
    ):
        raise ValueError("Run real có trace hoặc cấu hình fake")
    return rows


def draft_review(run) -> dict:
    return {
        "schema_version": 1,
        "run_id": run["run_id"],
        "run_digest": digest(run),
        "source": "pending",
        "reviewer": "",
        "cases": [
            {
                "name": c["name"],
                "syllabus_sha256": c["syllabus_sha256"],
                "gold_sha256": c["gold_sha256"],
                "approved": None,
                "note": "",
            }
            for c in _rows(run)
        ],
    }


def _approved(run, review) -> bool:
    if review is None:
        return False
    if not isinstance(review, dict):
        raise ValueError("Review phải là object")
    expected = draft_review(run)
    if any(review.get(k) != expected[k] for k in ("schema_version", "run_id", "run_digest")):
        raise ValueError("Review không khớp run hoặc bằng chứng đã thay đổi")
    cases = review.get("cases", [])
    by_name = {c["name"]: c for c in cases}
    if len(by_name) != len(cases) or set(by_name) != {c["name"] for c in expected["cases"]}:
        raise ValueError("Review thiếu/trùng/thừa cặp dữ liệu")
    for want in expected["cases"]:
        got = by_name[want["name"]]
        if any(got.get(k) != want[k] for k in ("syllabus_sha256", "gold_sha256")):
            raise ValueError("Review không khớp hash giáo trình/cây chuẩn")
        if got.get("approved") is not None and type(got["approved"]) is not bool:
            raise ValueError("approved phải là true/false/null")
    if review.get("source") not in {"pending", "human"}:
        raise ValueError("Review source chỉ nhận pending/human")
    reviewer = review.get("reviewer")
    if review["source"] == "human" and (not isinstance(reviewer, str) or not reviewer.strip()):
        raise ValueError("Cần tên người duyệt thật")
    return review["source"] == "human" and all(c.get("approved") is True for c in cases)


def summarize(run, review=None) -> dict:
    rows = _rows(run)
    approved = _approved(run, review)
    scores = []
    for row in rows:
        if row["error"] is not None or row["prediction"] is None:
            continue
        data = row["gold"]
        gold = datasets.GoldTree(
            row["name"],
            data["subject"],
            data.get("syllabus"),
            TreeVersion.model_validate(data),
            data.get("aliases", {}),
        )
        scores.append(metrics.evaluate_tree(TreeVersion.model_validate(row["prediction"]), gold))
    total = metrics.aggregate(scores)
    processed = len(scores) == len(rows)
    source_hashes = {row.get("syllabus_sha256") for row in rows}
    complete = (
        processed
        and 3 <= len(rows) <= 5
        and len(source_hashes) == len(rows)
        and all(isinstance(value, str) and len(value) == 64 for value in source_hashes)
        and all(
            {"extract_seconds", "build_seconds", "sanitize_seconds"} <= row["timings"].keys()
            and bool(row["gold"]["edges"])
            for row in rows
        )
    )
    if run["mode"] == "real":
        configured = {
            (c.get("provider"), c.get("model"))
            for c in run.get("gateway_config", [])
            if c.get("provider") and c.get("model")
        }
        successful_cases = {
            c.get("case")
            for c in run.get("gateway_calls", [])
            if c.get("outcome") == "ok" and (c.get("provider"), c.get("model")) in configured
        }
        complete = complete and {row["name"] for row in rows} <= successful_cases
    target = None
    if run["mode"] == "fake":
        status = "SIMULATION"
    elif not complete:
        status = "INCOMPLETE"
    elif not approved:
        status = "NEEDS_REVIEW"
    else:
        f1s = [total["edges"][kind]["f1"] for kind in ("micro", "macro")]
        target = all(value is not None and value >= 0.70 for value in f1s)
        status = "PARTIAL_SCOPE" if target else "FAILED"
    return {
        "status": status,
        "cases": len(rows),
        "scored_cases": len(scores),
        "processed_all": processed,
        "benchmark_complete": complete,
        "gold_approved": approved,
        "edge_target_met": target,
        "pipeline_seconds": None,
        "aggregate": total,
        "scores": scores,
    }


def markdown(run, review=None) -> str:
    result = summarize(run, review)
    scores = {s["name"]: s for s in result["scores"]}

    def number(value):
        return "—" if value is None else f"{value:.3f}"

    def prf(score):
        return " / ".join(number(score[k]) for k in ("precision", "recall", "f1"))

    lines = [
        "# KT-09 – " + result["status"],
        "",
        f"- Run `{run['run_id']}` · mode `{run['mode']}` · {result['scored_cases']}/{result['cases']} cặp đo được.",
        "- Fake / cây chuẩn chưa được GV xác nhận chỉ kiểm luồng, không chứng minh chất lượng AI.",
        "- Phạm vi: bóc chữ/OCR → TreeBuilder → hậu xử lý DAG. Chưa đo upload/queue/RAG/rubric/UI.",
        "- Chưa có thời gian upload → tree.generated; KHÔNG kết luận MT1 ≤ 3 phút cho ~30 trang.",
        "",
        "| Cặp | Trang | P/R/F1 nút | P/R/F1 cạnh | Bóc chữ (s) | Sinh cây (s) | DAG (s) | Lỗi |",
        "|---|---:|---|---|---:|---:|---:|---|",
    ]
    for row in run["cases"]:
        score = scores.get(row["name"])
        timings = row["timings"]
        lines.append(
            f"| {row['name']} | {row['page_count']} | {prf(score['nodes']) if score else '—'} | "
            f"{prf(score['edges']) if score else '—'} | {number(timings.get('extract_seconds'))} | "
            f"{number(timings.get('build_seconds'))} | {number(timings.get('sanitize_seconds'))} | "
            f"{row['error'] or '—'} |"
        )
    lines.extend(["", "| Tổng hợp | P/R/F1 nút | P/R/F1 cạnh |", "|---|---|---|"])
    for kind in ("micro", "macro"):
        total = result["aggregate"]
        lines.append(f"| {kind} | {prf(total['nodes'][kind])} | {prf(total['edges'][kind])} |")
    lines.extend(
        [
            "",
            f"Đủ 3–5 giáo trình khác nhau và bằng chứng: {result['benchmark_complete']}; "
            f"GV xác nhận đủ: {result['gold_approved']}.",
            "Tổng hợp trên các cặp đo được; cặp lỗi vẫn giữ trong báo cáo và ngăn kết luận đủ bộ.",
            "Quy ước: kiểm cả micro/macro F1 cạnh ≥ 0,70. PARTIAL_SCOPE chỉ đạt phần chất lượng cây, chưa xong KT-09.",
            "Gateway log ghi lời gọi JSON; không có trace từng embedding. Không lưu prompt/khóa/lỗi thô của provider.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(run, output: Path) -> None:
    rendered = markdown(run)
    review = draft_review(run)
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (("run.json", run), ("review.json", review)):
        (output / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
    (output / "summary.md").write_text(rendered, encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collector = commands.add_parser("collect")
    collector.add_argument("--root", type=Path, default=ROOT / "evals", help="Thư mục chứa tree/*.gold.json")
    collector.add_argument("--case", action="append", help="Chọn mã cặp; mặc định thu tất cả, kể cả cặp thiếu file")
    collector.add_argument("--output", type=Path, required=True, help="Thư mục mới, không ghi đè")
    reporter = commands.add_parser("report")
    reporter.add_argument("--run", type=Path, required=True)
    reporter.add_argument("--review", type=Path, required=True)
    reporter.add_argument("--output", type=Path, help="File báo cáo mới")
    args = parser.parse_args(argv)
    try:
        if args.command == "report":
            run = json.loads(args.run.read_text(encoding="utf-8"))
            review = json.loads(args.review.read_text(encoding="utf-8"))
            result = summarize(run, review)
            rendered = markdown(run, review)
            if args.output:
                with args.output.open("x", encoding="utf-8") as stream:
                    stream.write(rendered)
            print(rendered)
            return 0 if result["status"] == "SIMULATION" and result["processed_all"] else 1
        from app.ai.gateway import build_gateway
        from app.core.config import get_settings

        cases = load_cases(args.root)
        if args.case:
            if len(set(args.case)) != len(args.case) or set(args.case) - {c.gold.name for c in cases}:
                raise ValueError("--case trùng hoặc không có trong bộ dữ liệu")
            cases = [c for c in cases if c.gold.name in args.case]
        settings = get_settings()
        if settings.demo_mode:
            raise ValueError("Cần DEMO_MODE=0")
        if args.output.exists():
            raise FileExistsError(f"Thư mục đã tồn tại: {args.output}")
        if settings.llm_mode == "real" and len(cases) > 5:
            raise ValueError("Bộ KT-09 tối đa 5 giáo trình trong một lượt")
        gateway = build_gateway(settings.model_copy(update={"app_env": "test", "llm_cache_size": 0}))
        try:
            run = collect(cases, gateway, mode=settings.llm_mode)
        finally:
            gateway.close()
        write_outputs(run, args.output)
        print(markdown(run))
        print(f"Bằng chứng và phiếu GV chờ duyệt: {args.output.resolve()}")
        return 0 if summarize(run)["processed_all"] else 1
    except (ValueError, OSError, KeyError, TypeError, AppError, datasets.DatasetError) as exc:
        message = exc.code if isinstance(exc, AppError) else str(exc)
        print(f"KT-09: {message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
