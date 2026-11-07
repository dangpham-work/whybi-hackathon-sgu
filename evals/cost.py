"""Đo chi phí AI của một phiên giảng (tiêu chí VI – AI tiết kiệm chi phí).

Chạy lại đúng luồng của SessionOrchestrator bằng **model thật**, không cần CSDL:
câu mở đầu → (Guard đầu vào → bao phủ → câu hỏi phản biện + Guard đầu ra) × mỗi lượt SV → Judge.
Lời SV lấy từ `evals/tutee/sessions.jsonl`. Mỗi lời gọi LLM được đếm token qua log `llm.call` của gateway.

Chạy (từ backend/, cần khóa thật trong .env):
  uv run python ../evals/cost.py --phien=6 --cau-hinh=openai_compat:gpt-4o-mini,gemini:gemini-3.5-flash-lite --ghi
"""

from __future__ import annotations

import contextvars
import datetime
import statistics
import sys
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
sys.stdout.reconfigure(encoding="utf-8")

import eval_datasets as datasets  # noqa: E402

# USD / 1 triệu token (bậc Standard trả phí). Nguồn: developers.openai.com/api/docs/pricing,
# aistudio.google.com/docs/pricing – tra ngày 2026-11-07. Đổi giá thì sửa bảng này và ghi lại ngày.
GIA: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
}
TY_GIA = 26_000  # VND / USD – giả định làm tròn, chỉ để dễ hình dung
SO_CAU_HOI = 3  # challenge_count mặc định của lớp (FR-TB-08)
JUDGE_RUNS = 2  # như SessionOrchestrator
PHAN_TICH = "<!-- phan-tich: phần dưới viết tay, cost.py giữ nguyên khi đo lại -->"

# Tên schema → bước trong phiên (để bảng chi phí đọc được)
BUOC = {
    "TuteeUtterance": "Tutee sinh câu (mở đầu + phản biện)",
    "CoverageAnalysis": "Tutee phân tích bao phủ",
    "GuardVerdict": "Guard đầu vào (LLM, khi luật không quyết được)",
    "LeakVerdict": "Guard đầu ra (kiểm lộ đáp án)",
    "JudgeResult": "Judge chấm 5 tiêu chí",
}

_schema_hien_tai: contextvars.ContextVar[str] = contextvars.ContextVar("schema", default="?")


@dataclass
class LoiGoi:
    schema: str
    model: str
    vao: int
    ra: int
    ms: int
    ket_qua: str


@dataclass
class Phien:
    id: str
    goi: list[LoiGoi] = field(default_factory=list)
    giay: float = 0.0
    loi: str = ""

    def token(self) -> tuple[int, int]:
        return sum(g.vao for g in self.goi), sum(g.ra for g in self.goi)


def chi_phi(model: str, vao: float, ra: float) -> float:
    gia_vao, gia_ra = GIA[model]
    return (vao * gia_vao + ra * gia_ra) / 1_000_000


def gan_dem(gw, phien_ref: list[Phien | None]) -> None:
    """Gói call_json để biết schema, và _log/_log_error để ghi lại token của từng lời gọi tới nhà cung cấp."""
    goc_call, goc_log, goc_err = gw.call_json, gw._log, gw._log_error

    def call_json(schema, *a, **kw):
        tok = _schema_hien_tai.set(schema.__name__)
        try:
            return goc_call(schema, *a, **kw)
        finally:
            _schema_hien_tai.reset(tok)

    def _log(provider, model, result, outcome, *a, **kw):
        if phien_ref[0] is not None:
            phien_ref[0].goi.append(
                LoiGoi(
                    _schema_hien_tai.get(),
                    model,
                    result.input_tokens,
                    result.output_tokens,
                    result.latency_ms,
                    outcome,
                )
            )
        return goc_log(provider, model, result, outcome, *a, **kw)

    def _log_error(provider, model, err, t0, *a, **kw):
        if phien_ref[0] is not None:
            ms = int((time.perf_counter() - t0) * 1000)
            phien_ref[0].goi.append(LoiGoi(_schema_hien_tai.get(), model, 0, 0, ms, f"error:{type(err).__name__}"))
        return goc_err(provider, model, err, t0, *a, **kw)

    gw.call_json, gw._log, gw._log_error = call_json, _log, _log_error


def chay_phien(s, node, tutee, guard, judge) -> None:
    """Một phiên theo đúng thứ tự của SessionOrchestrator (_handle_turn → _advance → _finish)."""
    from app.ai.agents.tutee import SessionContext

    sid = str(uuid.uuid4())  # mỗi phiên một id ⇒ ngân sách token phiên áp như thật
    transcript: list[dict] = [{"role": "tutee", "text": tutee.opening_line(node, session_id=sid).text}]
    asked = []
    for t in (t for t in s.turns if t.role == "student"):
        g = guard.check_input(t.text, node.title, session_id=sid)
        if g.blocked:
            continue
        transcript.append({"role": "student", "text": t.text})
        coverage = tutee.analyze_coverage([x for x in transcript if x["role"] == "student"], node, session_id=sid)
        ctx = SessionContext(
            node=node, transcript=transcript, coverage=coverage, asked=asked, max_questions=SO_CAU_HOI, session_id=sid
        )
        q = tutee.next_question(ctx)
        if q is None:
            break
        asked.append(q)
        transcript.append({"role": "tutee", "text": q.text})
    judge.evaluate(
        transcript,
        node.rubric,
        node.title,
        challenges_total=len(asked),
        min_passed_challenges=max(1, min(node.rubric.min_passed_challenges, len(asked))),
        session_id=sid,
    )


def do_cau_hinh(provider: str, model: str, so_phien: int) -> list[Phien]:
    from app.ai.agents.guard import GuardAgent
    from app.ai.agents.judge import JudgeAgent
    from app.ai.agents.tutee import TuteeAgent
    from app.ai.gateway import configure_llm
    from app.services.skill_tree import load_seed_tree

    gw = configure_llm(provider, model)  # không model dự phòng: đo riêng từng model
    ref: list[Phien | None] = [None]
    gan_dem(gw, ref)
    guard = GuardAgent(gw, model=model)
    tutee = TuteeAgent(gw, max_questions=SO_CAU_HOI, guard=guard, model=model)
    judge = JudgeAgent(gw, runs=JUDGE_RUNS, model=model)
    nodes = {n.code: n for n in load_seed_tree().nodes}
    # lấy đều các nhóm kịch bản: phiên T01, T06, T11… (mỗi nhóm 5 phiên liên tiếp)
    tat_ca = [s for s in datasets.load_tutee() if nodes[s.node].rubric]
    buoc = max(1, len(tat_ca) // so_phien)
    chon = tat_ca[::buoc][:so_phien]
    out = []
    for s in chon:
        p = Phien(s.id)
        ref[0] = p
        t0 = time.perf_counter()
        try:
            chay_phien(s, nodes[s.node], tutee, guard, judge)
        except Exception as e:  # ghi lại, không bỏ qua: phiên lỗi vẫn hiện trong báo cáo
            p.loi = f"{type(e).__name__}: {e}"
        p.giay = time.perf_counter() - t0
        ref[0] = None
        vao, ra = p.token()
        print(
            f"  {s.id}: {len(p.goi)} lời gọi · {vao:,} vào / {ra:,} ra · ${chi_phi(model, vao, ra):.5f} · {p.giay:.1f}s"
            + (f" · LỖI {p.loi}" if p.loi else "")
        )
        out.append(p)
    return out


def bao_cao(ket_qua: dict[str, list[Phien]]) -> str:
    from app.core.config import get_settings

    budget = get_settings().llm_session_token_budget
    L = [
        "# Kết quả đánh giá – chi phí AI mỗi phiên (tiêu chí VI)",
        "",
        f"- Ngày chạy: {datetime.date.today()} · Công cụ: `evals/cost.py` · LLM_MODE=real, gọi API thật",
        "- Luồng: câu mở đầu → mỗi lượt SV (Guard đầu vào → bao phủ → câu hỏi + Guard đầu ra)"
        f" → Judge {JUDGE_RUNS} lần chấm; {SO_CAU_HOI} câu phản biện; lời SV lấy từ `evals/tutee/sessions.jsonl`",
        "- Giá: bậc Standard trả phí, tra ngày 2026-11-07 (OpenAI, Google AI Studio). "
        f"Quy đổi {TY_GIA:_} đ/USD (giả định làm tròn).".replace("_", "."),
        "",
        "## Tổng hợp",
        "",
        "| Model | Phiên đo | Lời gọi LLM / phiên | Token vào / phiên | Token ra / phiên | Token tối đa / ngân sách"
        " | Chi phí / phiên | Thời gian AI / phiên |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for model, ps in ket_qua.items():
        ok = [p for p in ps if not p.loi]
        if not ok:
            L.append(f"| {model} | 0/{len(ps)} | – | – | – | – | – | – |")
            continue
        vao = statistics.mean(p.token()[0] for p in ok)
        ra = statistics.mean(p.token()[1] for p in ok)
        tmax = max(sum(p.token()) for p in ok)
        usd = chi_phi(model, vao, ra)
        so_goi = statistics.mean(len(p.goi) for p in ok)
        giay = statistics.mean(p.giay for p in ok)
        L.append(
            f"| `{model}` | {len(ok)}/{len(ps)} | {so_goi:.1f} | {vao:,.0f} | {ra:,.0f} | {tmax:,} / {budget:,}"
            f" | **${usd:.4f}** (≈ {usd * TY_GIA:,.0f} đ) | {giay:.1f}s |"
        )
    L += ["", "## Chi phí theo bước (trung bình mỗi phiên)", ""]
    for model, ps in ket_qua.items():
        ok = [p for p in ps if not p.loi]
        if not ok:
            continue
        theo: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        for p in ok:
            for g in p.goi:
                theo[g.schema][0] += 1
                theo[g.schema][1] += g.vao
                theo[g.schema][2] += g.ra
        tong = chi_phi(model, *map(sum, zip(*[p.token() for p in ok], strict=True))) or 1
        L += [f"**`{model}`**", "", "| Bước | Lời gọi | Token vào | Token ra | Tỉ trọng chi phí |"]
        L.append("|---|---|---|---|---|")
        for schema, (n, v, r) in sorted(theo.items(), key=lambda kv: -chi_phi(model, kv[1][1], kv[1][2])):
            k = len(ok)
            L.append(
                f"| {BUOC.get(schema, schema)} | {n / k:.1f} | {v / k:,.0f} | {r / k:,.0f}"
                f" | {chi_phi(model, v, r) / tong:.0%} |"
            )
        loi = [g for p in ok for g in p.goi if g.ket_qua != "ok"]
        if loi:
            L.append(
                f"\nLời gọi không thành công (đã tính token nếu có): {len(loi)} – "
                + ", ".join(sorted({g.ket_qua for g in loi}))
            )
        L.append("")
    hong = [(m, p) for m, ps in ket_qua.items() for p in ps if p.loi]
    if hong:
        L += ["## Phiên lỗi", ""] + [f"- `{m}` {p.id}: {p.loi}" for m, p in hong] + [""]
    L.append("")
    return "\n".join(L).replace("\n\n\n", "\n\n")


def main(argv: list[str]) -> int:
    from app.core.config import get_settings

    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--") and "=" in a)
    if get_settings().llm_mode != "real":
        print("Cần LLM_MODE=real: đo chi phí bằng LLM giả là vô nghĩa.", file=sys.stderr)
        return 1
    so_phien = int(opts.get("phien", "6"))
    cau_hinh = [c.split(":", 1) for c in opts.get("cau-hinh", "openai_compat:gpt-4o-mini").split(",")]
    ket_qua = {}
    for provider, model in cau_hinh:
        if model not in GIA:
            print(f"Chưa có giá cho {model}, thêm vào bảng GIA trước.", file=sys.stderr)
            return 1
        print(f"\n== {provider}/{model} ({so_phien} phiên) ==")
        ket_qua[model] = do_cau_hinh(provider, model, so_phien)
    md = bao_cao(ket_qua)
    print("\n" + md)
    if "--ghi" in argv:
        out = DIR / "results" / "cost.md"
        cu = out.read_text(encoding="utf-8") if out.exists() else ""
        if PHAN_TICH in cu:  # giữ phần phân tích viết tay khi đo lại
            md = md.rstrip() + "\n\n" + cu[cu.index(PHAN_TICH) :]
        out.write_text(md, encoding="utf-8")
        print(f"Đã ghi {DIR / 'results' / 'cost.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
