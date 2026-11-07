"""KT-10: đo SpeechService trước chỉnh sửa của SV, không coi fake là chất lượng STT thật."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import math
import subprocess
import sys
import time
import wave
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evals"))

import eval_datasets as datasets  # noqa: E402

from app.ai.providers.base import ProviderError  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.models.schemas.tree import Node  # noqa: E402
from app.services.speech import MAX_AUDIO_BYTES, MemoryAudioStore, SpeechService, validate_audio  # noqa: E402

_spec = importlib.util.spec_from_file_location("kt10_stt_metrics", Path(__file__).with_name("metrics.py"))
metrics = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = metrics
_spec.loader.exec_module(metrics)


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()


def provenance() -> dict:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=5).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True, timeout=5))
    except (OSError, subprocess.SubprocessError):
        commit, dirty = None, None
    paths = [
        Path(__file__),
        Path(__file__).with_name("metrics.py"),
        ROOT / "backend/app/services/speech.py",
        ROOT / "backend/app/ai/providers/stt.py",
        ROOT / "evals/eval_datasets.py",
    ]
    return {
        "commit": commit,
        "dirty": dirty,
        "python": sys.version.split()[0],
        "files": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
    }


@dataclass
class Case:
    clip: datasets.SttClip
    path: Path
    node: Node | None = None


def load_cases(root: Path = ROOT / "evals", contexts: dict | None = None) -> list[Case]:
    clips = datasets.load_stt(root)
    contexts = contexts or {}
    if set(contexts) - {c.id for c in clips}:
        raise ValueError("Context có mã không thuộc manifest")
    return [
        Case(c, root / "stt" / c.file, Node.model_validate(contexts[c.id]) if c.id in contexts else None) for c in clips
    ]


def audio_seconds(data: bytes) -> float:
    if data[:4] == b"RIFF":
        with wave.open(io.BytesIO(data), "rb") as stream:
            seconds = stream.getnframes() / stream.getframerate()
    else:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "format=duration:packet=pts_time,duration_time",
                "-of",
                "json",
                "-i",
                "pipe:0",
            ],
            input=data,
            capture_output=True,
            check=True,
            timeout=20,
        )
        body = json.loads(result.stdout)
        value = body.get("format", {}).get("duration")
        if value not in (None, "N/A"):
            seconds = float(value)
        else:
            packets = [
                (float(p["pts_time"]), float(p.get("duration_time", 0)))
                for p in body.get("packets", [])
                if "pts_time" in p
            ]
            if not packets or any(not math.isfinite(t) or not math.isfinite(d) or d < 0 for t, d in packets):
                raise ValueError("Không đo được thời lượng audio")
            seconds = max(t + d for t, d in packets) - min(t for t, _ in packets)
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("duration không hợp lệ")
    return seconds


class MeasuredProvider:
    """Đo ở ranh giới adapter, giữ bản chép thô trước chuẩn hóa; SpeechService vẫn tự retry."""

    def __init__(self, provider, clock):
        self.provider, self.clock = provider, clock
        self.name, self.model = provider.name, provider.model
        self.raw = None
        self.seconds = 0.0
        self.attempts = 0

    def transcribe(self, audio, lang="vi", hints=None):
        started = self.clock()
        self.attempts += 1
        try:
            self.raw = self.provider.transcribe(audio, lang, hints)
            return self.raw
        except ProviderError as exc:
            # SpeechService ghi exception vào log; chỉ đưa mã cố định qua ranh giới này.
            raise type(exc)("KT10_STT_PROVIDER_ERROR") from None
        finally:
            self.seconds += self.clock() - started


def collect(cases, provider, *, mode: str, clock=time.perf_counter) -> dict:
    if mode not in {"fake", "real"} or provider.name not in {"fake", "whisper", "cloud"}:
        raise ValueError("mode/provider không hợp lệ")
    if (mode == "fake") != (provider.name == "fake"):
        raise ValueError("provider không khớp mode; không gắn fake thành real")
    if get_settings().demo_mode:
        raise ValueError("Cần DEMO_MODE=0")
    if not cases or len({c.clip.id for c in cases}) != len(cases):
        raise ValueError("Bộ dữ liệu rỗng hoặc trùng id")
    # Kiểm reference/terms trước khi có thể gọi nhà cung cấp.
    for case in cases:
        metrics.term_accuracy(case.clip.reference, case.clip.reference, case.clip.terms)
    run = {
        "schema_version": 1,
        "run_id": str(uuid4()),
        "mode": mode,
        "cases": [],
        "created_at": datetime.now(UTC).isoformat(),
        "scope": "speech_service_no_storage",
        "provider": {"name": provider.name, "model": provider.model},
        "min_confidence": get_settings().stt_min_confidence,
        "provenance": provenance(),
        "warmup": "none",
    }
    for case in cases:
        row = {
            **case.clip.model_dump(),
            "errors": [],
            "audio_sha256": None,
            "node": case.node.model_dump(by_alias=True, mode="json") if case.node else None,
            "duration_seconds": None,
            "raw_text": None,
            "transcript": None,
            "service_seconds": None,
            "provider_seconds": None,
            "provider_attempts": 0,
            "provider": provider.name,
            "model": provider.model,
        }
        if not case.path.is_file():
            row["errors"].append("MISSING_AUDIO")
        if not case.clip.consent:
            row["errors"].append("CONSENT_REQUIRED")
        run["cases"].append(row)
        if row["errors"]:
            continue
        try:
            if case.path.stat().st_size > MAX_AUDIO_BYTES:
                raise AppError(413, "AUDIO_TOO_LARGE", "Tệp vượt giới hạn")
            data = case.path.read_bytes()
            validate_audio(data)
            row["audio_sha256"] = hashlib.sha256(data).hexdigest()
            try:
                row["duration_seconds"] = audio_seconds(data)
            except (OSError, ValueError, KeyError, wave.Error, EOFError, subprocess.SubprocessError):
                row["errors"].append("DURATION_UNAVAILABLE")
                continue
            if row["duration_seconds"] > 180:
                row["errors"].append("AUDIO_TOO_LONG")
                continue
            measured = MeasuredProvider(provider, clock)
            service = SpeechService(stt=measured, store=MemoryAudioStore())
            started = clock()
            try:
                # Đồng ý dùng giọng trong manifest khác với lưu thêm bản ghi vào kho sản phẩm.
                transcript = service.transcribe(data, case.node, session_id=uuid4(), consent=False)
            finally:
                row["service_seconds"] = clock() - started
                row["provider_seconds"] = measured.seconds
                row["provider_attempts"] = measured.attempts
            row["raw_text"] = measured.raw.text
            row["transcript"] = transcript.model_dump(by_alias=True, mode="json")
        except AppError as exc:
            row["errors"].append(exc.code)
        except OSError:
            row["errors"].append("AUDIO_READ_FAILED")
    return run


def draft_review(run) -> dict:
    return {
        "schema_version": 1,
        "run_id": run["run_id"],
        "run_digest": digest(run),
        "source": "pending",
        "reviewer": "",
        "approved": None,
        "note": "Đối chiếu reference, consent, speaker, nút và thời lượng; không duyệt dữ liệu tổng hợp.",
    }


def summarize(run, review=None) -> dict:
    if run.get("schema_version") != 1 or run.get("scope") != "speech_service_no_storage":
        raise ValueError("Run sai schema/scope")
    mode, provider = run.get("mode"), run["provider"]
    if mode not in {"fake", "real"} or provider["name"] not in {"fake", "whisper", "cloud"}:
        raise ValueError("mode/provider không hợp lệ")
    if (mode == "fake") != (provider["name"] == "fake"):
        raise ValueError("provider không khớp mode")
    if not run["cases"] or len({r["id"] for r in run["cases"]}) != len(run["cases"]):
        raise ValueError("Run rỗng hoặc trùng id")
    approved = False
    if review is not None:
        expected = draft_review(run)
        if any(review.get(k) != expected[k] for k in ("schema_version", "run_id", "run_digest")):
            raise ValueError("review không khớp run hoặc bằng chứng đã thay đổi")
        if review.get("source") not in {"pending", "human"}:
            raise ValueError("review source không hợp lệ")
        flag = review.get("approved")
        if flag is not None and type(flag) is not bool:
            raise ValueError("review approved phải là true/false/null")
        reviewer = review.get("reviewer")
        if review["source"] == "human" and (not isinstance(reviewer, str) or not reviewer.strip()):
            raise ValueError("review cần tên người duyệt thật")
        approved = review["source"] == "human" and flag is True
    rows = [r for r in run["cases"] if not r["errors"]]
    for row in rows:
        metrics.p95([row["service_seconds"], row["provider_seconds"], row["duration_seconds"]])
        if row["service_seconds"] < row["provider_seconds"]:
            raise ValueError("thời gian service phải bao gồm thời gian provider")
        if row["provider"] != provider["name"] or row["model"] != provider["model"]:
            raise ValueError("provider/model của mẫu không khớp run")
        if row["node"] is not None:
            Node.model_validate(row["node"])
    normalized = [metrics.word_errors(r["reference"], r["transcript"]["text"]) for r in rows]
    raw = [metrics.word_errors(r["reference"], r["raw_text"]) for r in rows]
    terms = [metrics.term_accuracy(r["reference"], r["transcript"]["text"], r["terms"]) for r in rows]
    term_total = sum(t["total"] for t in terms)
    sixty = [r for r in rows if abs(r["duration_seconds"] - 60) <= 0.5]
    hashes = {r["audio_sha256"] for r in rows}
    speakers = {r["speaker"].strip() for r in rows if isinstance(r["speaker"], str) and r["speaker"].strip()}
    complete = (
        len(rows) == len(run["cases"]) >= 30
        and len(hashes) == len(rows)
        and all(isinstance(h, str) and len(h) == 64 and all(c in "0123456789abcdef" for c in h) for h in hashes)
        and len(speakers) >= 2
        and all(
            r["consent"] is True
            and r["node"] is not None
            and isinstance(r["speaker"], str)
            and r["speaker"].strip()
            and 30 <= r["duration_seconds"] <= 120
            and type(r["provider_attempts"]) is int
            and r["provider_attempts"] >= 1
            for r in rows
        )
    )
    wer = metrics.corpus_wer(normalized)
    latency = metrics.p95([r["service_seconds"] for r in sixty])
    quality_met = latency_met = None
    if mode == "fake":
        status = "SIMULATION"
    elif not complete:
        status = "INCOMPLETE"
    elif not approved:
        status = "NEEDS_REVIEW"
    else:
        quality_met = wer <= 0.15
        latency_met = latency <= 4 if len(sixty) >= 20 else None
        status = "FAILED" if quality_met is False or latency_met is False else "PARTIAL_SCOPE"
    return {
        "status": status,
        "total": len(run["cases"]),
        "complete": complete,
        "reviewed": approved,
        "scored": len(rows),
        "wer": wer,
        "raw_wer": metrics.corpus_wer(raw),
        "term_accuracy": sum(t["correct"] for t in terms) / term_total if term_total else None,
        "p95_service_seconds": metrics.p95([r["service_seconds"] for r in rows]),
        "p95_sixty_seconds": latency,
        "sixty_second_samples": len(sixty),
        "quality_target_met": quality_met,
        "latency_target_met": latency_met,
    }


def markdown(run, review=None) -> str:
    summary = summarize(run, review)

    def number(value):
        return "—" if value is None else f"{value:.3f}"

    lines = [
        f"# KT-10 – {summary['status']}",
        "",
        f"- Run `{run['run_id']}`; {summary['scored']}/{summary['total']} mẫu đo được.",
        f"- Provider/model: {run['provider']['name']}/{run['provider']['model']}; mode={run['mode']}.",
        "- Đo SpeechService trước chỉnh sửa của SV, không lưu thêm âm thanh vào MinIO; không đo HTTP/UI.",
        "- Thời gian bao gồm retry, không warm-up riêng; bóc metadata thời lượng ngoài khoảng đo.",
        "- Fake chỉ kiểm công cụ. PARTIAL_SCOPE không có nghĩa là nghiệm thu toàn bộ KT-10/NFR-02.",
        "",
        "| Mẫu | Giây âm thanh | WER thô | WER sau chuẩn hóa | Thuật ngữ đúng | STT (s) | Service (s) | Lỗi |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in run["cases"]:
        raw = normalized = terms = None
        if not row["errors"]:
            raw = metrics.word_errors(row["reference"], row["raw_text"])["wer"]
            normalized = metrics.word_errors(row["reference"], row["transcript"]["text"])["wer"]
            terms = metrics.term_accuracy(row["reference"], row["transcript"]["text"], row["terms"])["accuracy"]
        lines.append(
            f"| {row['id']} | {number(row['duration_seconds'])} | {number(raw)} | {number(normalized)} | "
            f"{number(terms)} | {number(row['provider_seconds'])} | {number(row['service_seconds'])} | "
            f"{', '.join(row['errors']) or '—'} |"
        )
    lines += [
        "",
        f"- WER corpus: {number(summary['wer'])}; WER thô: {number(summary['raw_wer'])}.",
        f"- Tỉ lệ thuật ngữ đúng: {number(summary['term_accuracy'])}.",
        f"- p95 service toàn bộ: {number(summary['p95_service_seconds'])} s (chỉ mẫu thành công).",
        f"- p95 nhóm 60±0,5 s: {number(summary['p95_sixty_seconds'])} s; {summary['sixty_second_samples']} mẫu.",
        f"- Đủ bộ: {summary['complete']}; người duyệt xác nhận: {summary['reviewed']}.",
        f"- WER ≤ 15%: {summary['quality_target_met']}; p95 nhóm 60 s ≤ 4 s: {summary['latency_target_met']}.",
        "- Mẫu lỗi vẫn trong tổng số và ngăn công nhận đủ bộ. Cần ≥20 mẫu 60 s để xét ngưỡng p95 nhóm này.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(run, output: Path) -> None:
    report, review = markdown(run), draft_review(run)
    output.mkdir(parents=True, exist_ok=False)
    for name, data in (("run.json", run), ("review.json", review)):
        (output / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
    (output / "summary.md").write_text(report, encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collector = commands.add_parser("collect")
    collector.add_argument("--root", type=Path, default=ROOT / "evals", help="Chứa stt/manifest.jsonl và stt/audio/")
    collector.add_argument(
        "--contexts", type=Path, help="JSON {S01: Node, ...}, ngữ cảnh thật của nút; không lấy từ reference"
    )
    collector.add_argument("--output", type=Path, required=True, help="Thư mục mới, không ghi đè")
    reporter = commands.add_parser("report")
    reporter.add_argument("--run", type=Path, required=True)
    reporter.add_argument("--review", type=Path, required=True)
    reporter.add_argument("--output", type=Path, help="File Markdown mới")
    args = parser.parse_args(argv)
    try:
        if args.command == "report":
            run = json.loads(args.run.read_text(encoding="utf-8"))
            review = json.loads(args.review.read_text(encoding="utf-8"))
            rendered = markdown(run, review)
            if args.output:
                with args.output.open("x", encoding="utf-8") as stream:
                    stream.write(rendered)
            print(rendered)
            result = summarize(run, review)
            return 0 if run["mode"] == "fake" and result["scored"] == result["total"] else 1
        from app.ai.providers.stt import build_stt_provider

        if args.output.exists():
            raise FileExistsError("Thư mục đầu ra đã tồn tại")
        contexts = json.loads(args.contexts.read_text(encoding="utf-8")) if args.contexts else None
        cases = load_cases(args.root, contexts)
        settings = get_settings()
        provider = build_stt_provider(settings)
        try:
            run = collect(cases, provider, mode=settings.llm_mode)
        finally:
            if getattr(provider, "http", None) is not None:
                provider.http.close()
        write_outputs(run, args.output)
        print(markdown(run))
        print(f"Bằng chứng: {args.output.resolve()}")
        result = summarize(run)
        return 0 if result["scored"] == result["total"] else 1
    except ProviderError:
        print("KT-10: STT_PROVIDER_CONFIG_ERROR", file=sys.stderr)
        return 2
    except (ValueError, TypeError, KeyError, OSError, AppError, datasets.DatasetError) as exc:
        print(f"KT-10: {exc.code if isinstance(exc, AppError) else exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
