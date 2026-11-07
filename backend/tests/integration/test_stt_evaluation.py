"""KT-10: chỉ số và CLI STT; dữ liệu tổng hợp chỉ kiểm công cụ, không đo chất lượng AI."""

import copy
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def metrics():
    return load_module("kt10_metrics", ROOT / "evals/stt/metrics.py")


def test_wer_counts_substitution_deletion_insertion_without_capping_at_one(metrics):
    assert metrics.word_errors("a b c", "a x c d") == {
        "reference_words": 3,
        "substitutions": 1,
        "deletions": 0,
        "insertions": 1,
        "wer": pytest.approx(2 / 3),
    }
    assert metrics.word_errors("a b c", "a c")["deletions"] == 1
    assert metrics.word_errors("a", "x y z")["wer"] == 3


def test_terms_count_each_aligned_occurrence_not_substrings_or_extra_mentions(metrics):
    assert metrics.term_accuracy("malloc rồi malloc và free", "malloc rồi mất và free", ["malloc", "free"]) == {
        "correct": 2,
        "total": 3,
        "accuracy": pytest.approx(2 / 3),
    }
    assert metrics.term_accuracy("con trỏ", "con rất trỏ", ["con trỏ"])["correct"] == 0
    assert metrics.term_accuracy("free", "freezer", ["free"])["correct"] == 0
    with pytest.raises(ValueError, match="reference"):
        metrics.term_accuracy("con trỏ", "malloc", ["malloc"])


def test_normalization_preserves_vietnamese_and_operator_meaning(metrics):
    assert metrics.word_errors("CON TRỎ, C++!", "con trỏ c++")["wer"] == 0
    assert metrics.word_errors("trỏ", "tro")["wer"] == 1
    assert metrics.word_errors("C++", "C")["wer"] == 1
    assert metrics.word_errors("con trỏ", "")["deletions"] == 2
    with pytest.raises(ValueError):
        metrics.word_errors("...", "anything")


def test_aggregate_weights_wer_by_words_and_p95_by_nearest_rank(metrics):
    scores = [metrics.word_errors("a", "x"), metrics.word_errors("a b c d e f g h i", "a b c d e f g h i")]
    assert metrics.corpus_wer(scores) == 0.1  # Không phải trung bình 0.5 của hai WER.
    assert metrics.p95(list(range(1, 21))) == 19
    assert metrics.p95([4]) == 4
    assert metrics.p95([]) is None
    assert metrics.corpus_wer([]) is None


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf"), True, "4"])
def test_latency_rejects_invalid_measurements(metrics, bad):
    with pytest.raises(ValueError):
        metrics.p95([bad])


@pytest.fixture
def runner():
    return load_module("kt10_evaluate", ROOT / "evals/stt/evaluate.py")


def wav(seconds=60):
    data = io.BytesIO()
    with wave.open(data, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b"\0\0" * (8000 * seconds))
    return data.getvalue()


def test_collect_keeps_all_30_missing_files_and_never_calls_provider(runner):
    class NoCalls:
        name = model = "fake"

        def transcribe(self, *args, **kwargs):
            pytest.fail("Thiếu file/consent phải bị chặn trước provider")

    run = runner.collect(runner.load_cases(), NoCalls(), mode="fake")
    assert len(run["cases"]) == 30
    assert all(set(row["errors"]) == {"MISSING_AUDIO", "CONSENT_REQUIRED"} for row in run["cases"])
    result = runner.summarize(run)
    assert result["status"] == "SIMULATION" and result["scored"] == 0
    assert result["wer"] is None and result["p95_service_seconds"] is None
    assert result["quality_target_met"] is None and result["latency_target_met"] is None


@pytest.fixture
def sample(runner, tmp_path):
    from app.models.schemas.tree import Node

    path = tmp_path / "sample.wav"
    path.write_bytes(wav())
    clip = runner.datasets.SttClip(
        id="S01", file="audio/S01.wav", reference="Con trỏ là biến", terms=["con trỏ"], consent=True, speaker="fixture"
    )
    return runner.Case(clip, path, Node(key="pointer", title="Con trỏ"))


class ScriptedSTT:
    name = model = "fake"

    def transcribe(self, audio, lang="vi", hints=None):
        from app.ai.providers.base import TranscriptResult

        assert audio[:4] == b"RIFF" and lang == "vi"
        assert "Con trỏ" in hints
        assert "Con trỏ là biến" not in hints  # reference không được lọt vào prompt.
        return TranscriptResult(text="Con chỏ là biến", confidence=0.65, words=[])


def test_collect_measures_service_and_raw_stt_before_student_edits(runner, sample):
    ticks = iter([10.0, 11.0, 13.0, 14.0])
    run = runner.collect([sample], ScriptedSTT(), mode="fake", clock=lambda: next(ticks))
    row = run["cases"][0]
    assert row["errors"] == [] and row["duration_seconds"] == 60
    assert row["raw_text"] == "Con chỏ là biến" and row["transcript"]["text"] == "Con trỏ là biến"
    assert row["transcript"]["needsConfirmation"] is True
    assert row["service_seconds"] == 4 and row["provider_seconds"] == 2
    assert row["provider_attempts"] == 1 and row["audio_sha256"]
    result = runner.summarize(run)
    assert result["raw_wer"] == 0.25 and result["wer"] == 0
    assert result["term_accuracy"] == 1 and result["p95_service_seconds"] == 4
    assert result["sixty_second_samples"] == 1 and result["latency_target_met"] is None


@pytest.mark.parametrize("mode,name", [("real", "fake"), ("fake", "cloud")])
def test_collect_rejects_provider_mode_mismatch_before_any_audio(runner, sample, mode, name):
    from types import SimpleNamespace

    with pytest.raises(ValueError, match="provider"):
        runner.collect([sample], SimpleNamespace(name=name, model=name), mode=mode)


def reviewed_fixture(runner, sample):
    """Bằng chứng tổng hợp CHỈ cho unit test; không ghi ra báo cáo nghiệm thu."""
    run = runner.collect([sample], ScriptedSTT(), mode="fake")
    run["mode"] = "real"
    run["provider"] = {"name": "whisper", "model": "unit-test-only"}
    template = run["cases"][0]
    run["cases"] = [copy.deepcopy(template) for _ in range(30)]
    for i, row in enumerate(run["cases"]):
        row.update(
            id=f"S{i + 1:02}",
            speaker=f"fixture-{i % 3}",
            audio_sha256=runner.digest(i),
            service_seconds=3.0,
            provider_seconds=2.0,
            provider="whisper",
            model="unit-test-only",
        )
    review = runner.draft_review(run)
    review.update(source="human", reviewer="Unit test fixture, not empirical evidence")
    review["approved"] = True
    return run, review


def test_report_requires_human_review_and_retains_partial_scope(runner, sample):
    run, review = reviewed_fixture(runner, sample)
    assert runner.summarize(run)["status"] == "NEEDS_REVIEW"
    result = runner.summarize(run, review)
    assert result["status"] == "PARTIAL_SCOPE"
    assert result["quality_target_met"] is True and result["latency_target_met"] is True
    run["cases"][0]["reference"] += " sửa"
    with pytest.raises(ValueError, match="review"):
        runner.summarize(run, review)


@pytest.mark.parametrize("defect", ["subset", "duplicate", "consent", "context", "speaker", "trace", "duration"])
def test_report_does_not_certify_incomplete_or_duplicated_dataset(runner, sample, defect):
    run, _ = reviewed_fixture(runner, sample)
    if defect == "subset":
        run["cases"].pop()
    elif defect == "duplicate":
        run["cases"][1]["audio_sha256"] = run["cases"][0]["audio_sha256"]
    elif defect == "consent":
        run["cases"][0]["consent"] = False
    elif defect == "context":
        run["cases"][0]["node"] = None
    elif defect == "speaker":
        for row in run["cases"]:
            row["speaker"] = None
    elif defect == "trace":
        run["cases"][0]["provider_attempts"] = 0
    else:
        run["cases"][0]["duration_seconds"] = 1
    assert runner.summarize(run)["status"] == "INCOMPLETE"


def test_short_clips_cannot_pass_the_sixty_second_latency_target(runner, sample):
    run, _ = reviewed_fixture(runner, sample)
    for row in run["cases"]:
        row["duration_seconds"] = 30
    review = runner.draft_review(run) | {"source": "human", "reviewer": "Unit test only", "approved": True}
    result = runner.summarize(run, review)
    assert result["quality_target_met"] is True
    assert result["sixty_second_samples"] == 0 and result["latency_target_met"] is None


@pytest.mark.parametrize("bad", ["true", None])
def test_human_review_requires_explicit_boolean_approval(runner, sample, bad):
    run, review = reviewed_fixture(runner, sample)
    review["approved"] = bad
    if bad is None:
        assert runner.summarize(run, review)["quality_target_met"] is None
    else:
        with pytest.raises(ValueError):
            runner.summarize(run, review)


def test_report_rejects_fake_provider_disguised_as_real(runner, sample):
    run = runner.collect([sample], ScriptedSTT(), mode="fake")
    run["mode"] = "real"
    with pytest.raises(ValueError, match="provider"):
        runner.summarize(run)


def test_write_artifacts_is_immutable_and_does_not_change_official_report(runner, sample, tmp_path):
    official = ROOT / "evals/results/stt.md"
    before = official.read_bytes()
    run = runner.collect([sample], ScriptedSTT(), mode="fake")
    out = tmp_path / "report"
    runner.write_outputs(run, out)
    assert "SIMULATION" in (out / "summary.md").read_text(encoding="utf-8")
    assert json.loads((out / "review.json").read_text(encoding="utf-8"))["approved"] is None
    with pytest.raises(FileExistsError):
        runner.write_outputs(run, out)
    assert official.read_bytes() == before


def test_cli_reports_all_missing_audio_and_offline_report(tmp_path):
    env = dict(os.environ, APP_ENV="test", LLM_MODE="fake", DEMO_MODE="0", PYTHONIOENCODING="ascii")
    out = tmp_path / "cli"
    base = [sys.executable, str(ROOT / "evals/stt/evaluate.py")]
    collected = subprocess.run(base + ["collect", "--output", str(out)], env=env, capture_output=True, timeout=30)
    assert collected.returncode == 1, collected.stderr.decode("utf-8", errors="replace")
    assert "0/30" in collected.stdout.decode("utf-8")
    reported = subprocess.run(
        base + ["report", "--run", str(out / "run.json"), "--review", str(out / "review.json")],
        env=env,
        capture_output=True,
        timeout=30,
    )
    assert reported.returncode == 1 and "SIMULATION" in reported.stdout.decode("utf-8")


def test_retry_counts_and_terminal_errors_remain_in_denominator(runner, sample):
    from app.ai.providers.base import TransientProviderError

    class RetrySTT(ScriptedSTT):
        attempts = 0

        def transcribe(self, *args, **kwargs):
            self.attempts += 1
            if self.attempts == 1:
                raise TransientProviderError("temporary fixture outage")
            return super().transcribe(*args, **kwargs)

    retry = runner.collect([sample], RetrySTT(), mode="fake")
    assert retry["cases"][0]["provider_attempts"] == 2 and runner.summarize(retry)["scored"] == 1

    class OfflineSTT(ScriptedSTT):
        def transcribe(self, *args, **kwargs):
            raise TransientProviderError("fixture outage")

    failed = runner.collect([sample], OfflineSTT(), mode="fake")
    assert failed["cases"][0]["errors"] == ["STT_UNAVAILABLE"]
    assert failed["cases"][0]["provider_attempts"] == 2
    assert runner.summarize(failed)["total"] == 1 and runner.summarize(failed)["scored"] == 0


def test_webm_without_header_duration_uses_audio_packet_timestamps(runner, monkeypatch):
    from types import SimpleNamespace

    def ffprobe(*args, **kwargs):
        return SimpleNamespace(
            stdout=json.dumps(
                {
                    "format": {},
                    "packets": [
                        {"pts_time": "-0.007", "duration_time": "0.020"},
                        {"pts_time": "59.973", "duration_time": "0.020"},
                    ],
                }
            ).encode()
        )

    monkeypatch.setattr(runner.subprocess, "run", ffprobe)
    assert runner.audio_seconds(b"\x1a\x45\xdf\xa3fixture") == pytest.approx(60)


def test_report_rejects_service_time_shorter_than_provider_time(runner, sample):
    run, _ = reviewed_fixture(runner, sample)
    run["cases"][0]["service_seconds"] = 1
    with pytest.raises(ValueError, match="thời gian"):
        runner.summarize(run)


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="cần ffmpeg/ffprobe; image backend có sẵn"
)
def test_real_ffprobe_measures_streamed_webm_without_duration_header(runner):
    encoded = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "wav", "-i", "pipe:0", "-c:a", "libopus", "-f", "webm", "pipe:1"],
        input=wav(60),
        capture_output=True,
        check=True,
        timeout=30,
    )
    assert runner.audio_seconds(encoded.stdout) == pytest.approx(60, abs=0.1)
