"""KT-13 – kiểm thử tải 20 / 50 / 100 phiên giảng đồng thời qua API thật (httpx + asyncio).

Không dùng k6/Locust (không thêm thư viện). Mỗi phiên ảo = một SV riêng:
đăng nhập → POST /sessions → POST /turns (lời giảng, rồi trả lời phản biện tới COMPLETED) → GET /result.
Mọi phiên trong một mức tải được thả cùng lúc (rào asyncio.Event) để đo đúng "N phiên đồng thời".

Chuẩn bị (không tính giờ): QTV tạo tài khoản SV riêng cho lần chạy (email `tai<tag>-<mức>-<i>@whybi.test`),
SV tham gia lớp mẫu `CTDL2026`; GV duyệt rubric + phát hành cây nếu cây còn nháp (như KT-05 --prepare-demo).
Mật khẩu QTV cấp chỉ giữ trong bộ nhớ, không in, không ghi file.

Chạy từ backend/ (stack đã seed bằng scripts/seed_db.py, backend LLM_MODE=fake):
    uv run python ../evals/perf/load_sessions.py --base http://localhost --levels 20,50,100

Kết quả: evals/results/perf.md (bảng), perf_box.svg (biểu đồ hộp + tỉ lệ lỗi), perf_raw.json (số thô).
LLM_MODE=fake ⇒ chỉ đo hạ tầng (API, CSDL, Redis); độ trễ LLM thật CHƯA tính.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import math
import os
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
SEED_PASSWORD = "Whybi@2026"  # mặc định dev: tài khoản giả công khai trong seed/README.md
MAX_TURNS = 12
LOGIN = "POST /auth/login"


# ------------------------------------------------------------------ bản ghi


@dataclass
class RequestRecord:
    endpoint: str  # "POST /sessions/{id}/turns" – gộp id để thống kê theo endpoint
    status: int  # 0 = không có phản hồi (timeout, mất kết nối)
    latency_ms: float
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.error is not None or self.status == 0 or self.status >= 400


@dataclass
class SessionRecord:
    index: int
    completed: bool
    duration_ms: float
    turns: int
    requests: list[RequestRecord] = field(default_factory=list)
    error: str | None = None


# ------------------------------------------------------------------ thống kê (hàm thuần)


def percentile(values, p):
    """Phân vị p (0–100), nội suy tuyến tính như numpy mặc định: vị trí (n-1)·p/100."""
    if not values:
        raise ValueError("không có giá trị để tính phân vị")
    if not 0 <= p <= 100:
        raise ValueError("p phải trong [0, 100]")
    xs = sorted(values)
    pos = (len(xs) - 1) * p / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _dist(values):
    if not values:
        return None
    return {
        "count": len(values),
        "min": min(values),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "max": max(values),
        "mean": sum(values) / len(values),
    }


def summarize(level, sessions, wall_ms):
    """Tóm tắt một mức tải. Độ trễ chỉ tính request thành công; lỗi đếm riêng (tỉ lệ lỗi)."""
    reqs = [r for s in sessions for r in s.requests]
    ok = [r.latency_ms for r in reqs if not r.failed]
    failed = [r for r in reqs if r.failed]
    errors_by_kind = {}
    for s in sessions:
        if s.error:
            errors_by_kind[s.error] = errors_by_kind.get(s.error, 0) + 1
    by_endpoint = {}
    for r in reqs:
        e = by_endpoint.setdefault(r.endpoint, {"count": 0, "errors": 0, "_ok": []})
        e["count"] += 1
        if r.failed:
            e["errors"] += 1
        else:
            e["_ok"].append(r.latency_ms)
    for e in by_endpoint.values():
        values = e.pop("_ok")
        e["p50"] = percentile(values, 50) if values else None
        e["p95"] = percentile(values, 95) if values else None
    session_errors = sum(1 for s in sessions if not s.completed)
    return {
        "level": level,
        "sessions": len(sessions),
        "requests": len(reqs),
        "requestErrors": len(failed),
        "requestErrorRate": len(failed) / len(reqs) if reqs else 0.0,
        "sessionErrors": session_errors,
        "sessionErrorRate": session_errors / len(sessions) if sessions else 0.0,
        "latencyMs": _dist(ok),
        "latencyNoLoginMs": _dist([r.latency_ms for r in reqs if not r.failed and r.endpoint != LOGIN]),
        "sessionMs": _dist([s.duration_ms for s in sessions if s.completed]),
        "turnsPerSession": _dist([s.turns for s in sessions if s.completed]),
        "wallMs": wall_ms,
        "throughputRps": len(reqs) / (wall_ms / 1000) if wall_ms else 0.0,
        "errorsByKind": errors_by_kind,
        "byEndpoint": by_endpoint,
    }


def box_stats(values):
    """Hộp Tukey: Q1, trung vị, Q3; râu tới điểm xa nhất trong 1,5·IQR; ngoài đó là điểm ngoại lai."""
    q1, med, q3 = percentile(values, 25), percentile(values, 50), percentile(values, 75)
    iqr = q3 - q1
    lo_fence, hi_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    inside = [v for v in values if lo_fence <= v <= hi_fence]
    return {
        "q1": q1,
        "median": med,
        "q3": q3,
        "whiskerLow": min(inside),
        "whiskerHigh": max(inside),
        "outliers": sorted(v for v in values if v < lo_fence or v > hi_fence),
    }


def _pct(rate):
    return f"{rate * 100:.1f}".replace(".", ",") + " %"


def _nice_max(v):
    if v <= 0:
        return 1
    mag = 10 ** math.floor(math.log10(v))
    for step in (1, 2, 2.5, 5, 10):
        if v <= step * mag:
            return step * mag
    return 10 * mag


def render_svg(levels, title):
    """SVG tĩnh hai khung (không trục kép): trái – hộp độ trễ request theo số phiên; phải – tỉ lệ lỗi (cột + nhãn số).

    `levels`: {số phiên: {"values": [ms…], "requestErrorRate": r, "sessionErrorRate": r}}.
    """
    ink, muted, grid, fill, stroke, bad = "#1f2328", "#59636e", "#d8dee4", "#9ec5fe", "#0b5cad", "#b42318"
    W, H, top, bottom = 920, 420, 70, 360
    keys = sorted(levels)
    all_vals = [v for k in keys for v in levels[k]["values"]] or [1]
    ymax = _nice_max(max(all_vals))
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        'font-family="system-ui, -apple-system, Segoe UI, sans-serif" font-size="12" role="img">',
        f"<title>{escape(title)}</title>",
        f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
        f'<text x="20" y="28" font-size="16" font-weight="600" fill="{ink}">{escape(title)}</text>',
    ]

    # Khung 1 – biểu đồ hộp
    x0, x1 = 80, 560
    out.append(f'<text x="{x0}" y="54" fill="{muted}">Độ trễ request thành công (ms) – hộp Q1–Q3, vạch = p50</text>')

    def y(v, vmax=ymax):
        return bottom - (bottom - top) * v / vmax

    for i in range(6):
        v = ymax * i / 5
        out.append(f'<line x1="{x0}" x2="{x1}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{grid}" stroke-width="1"/>')
        out.append(f'<text x="{x0 - 8}" y="{y(v) + 4:.1f}" text-anchor="end" fill="{muted}">{v:g}</text>')
    slot = (x1 - x0) / max(len(keys), 1)
    for i, k in enumerate(keys):
        cx = x0 + slot * (i + 0.5)
        vals = levels[k]["values"]
        out.append(f'<text x="{cx:.1f}" y="{bottom + 20}" text-anchor="middle" fill="{ink}">{k} phiên</text>')
        if not vals:
            out.append(
                f'<text x="{cx:.1f}" y="{bottom - 10}" text-anchor="middle" fill="{bad}">không có dữ liệu</text>'
            )
            continue
        b = box_stats(vals)
        hw = min(40, slot * 0.3)
        out.append(
            f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{y(b["whiskerLow"]):.1f}" y2="{y(b["whiskerHigh"]):.1f}" '
            f'stroke="{stroke}" stroke-width="2"/>'
        )
        for w in (b["whiskerLow"], b["whiskerHigh"]):
            out.append(
                f'<line x1="{cx - hw / 2:.1f}" x2="{cx + hw / 2:.1f}" y1="{y(w):.1f}" y2="{y(w):.1f}" '
                f'stroke="{stroke}" stroke-width="2"/>'
            )
        out.append(
            f'<rect x="{cx - hw:.1f}" y="{y(b["q3"]):.1f}" width="{2 * hw:.1f}" '
            f'height="{max(y(b["q1"]) - y(b["q3"]), 1):.1f}" rx="4" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
        )
        out.append(
            f'<line x1="{cx - hw:.1f}" x2="{cx + hw:.1f}" y1="{y(b["median"]):.1f}" y2="{y(b["median"]):.1f}" '
            f'stroke="{ink}" stroke-width="2"/>'
        )
        for o in b["outliers"][-200:]:
            out.append(f'<circle cx="{cx:.1f}" cy="{y(o):.1f}" r="2.5" fill="none" stroke="{muted}"/>')
        p95 = percentile(vals, 95)
        out.append(
            f'<text x="{cx + hw + 6:.1f}" y="{y(b["median"]) + 4:.1f}" fill="{ink}">p50 {b["median"]:.0f}</text>'
        )
        out.append(f'<text x="{cx + hw + 6:.1f}" y="{y(p95) + 4:.1f}" fill="{muted}">p95 {p95:.0f}</text>')

    # Khung 2 – tỉ lệ lỗi (thang 0–100 % riêng, khung riêng)
    x2, x3 = 640, 900
    out.append(f'<text x="{x2}" y="54" fill="{muted}">Tỉ lệ lỗi theo số phiên (request / phiên)</text>')
    rmax = _nice_max(max([levels[k]["requestErrorRate"] for k in keys] + [levels[k]["sessionErrorRate"] for k in keys]))
    rmax = min(max(rmax, 0.05), 1)
    for i in range(6):
        v = rmax * i / 5
        out.append(
            f'<line x1="{x2}" x2="{x3}" y1="{y(v, rmax):.1f}" y2="{y(v, rmax):.1f}" stroke="{grid}" stroke-width="1"/>'
        )
        out.append(f'<text x="{x2 - 6}" y="{y(v, rmax) + 4:.1f}" text-anchor="end" fill="{muted}">{v * 100:g}%</text>')
    slot2 = (x3 - x2) / max(len(keys), 1)
    for i, k in enumerate(keys):
        cx = x2 + slot2 * (i + 0.5)
        out.append(f'<text x="{cx:.1f}" y="{bottom + 20}" text-anchor="middle" fill="{ink}">{k} phiên</text>')
        for j, (name, rate, color) in enumerate(
            (("request", levels[k]["requestErrorRate"], stroke), ("phiên", levels[k]["sessionErrorRate"], bad))
        ):
            bw = 14
            bx = cx - bw - 1 + j * (bw + 2)
            h = max(bottom - y(rate, rmax), 0)
            out.append(f'<rect x="{bx:.1f}" y="{bottom - h:.1f}" width="{bw}" height="{h:.1f}" fill="{color}"/>')
            out.append(
                f'<text x="{cx:.1f}" y="{bottom + 34 + 13 * j}" text-anchor="middle" fill="{ink}" font-size="11">'
                f"{name}: {_pct(rate)}</text>"
            )
    out.append(
        f'<text x="{x2}" y="{H - 8}" fill="{muted}" font-size="11">'
        f"Cột trái (xanh) = request lỗi · cột phải (đỏ) = phiên không hoàn tất</text>"
    )
    out.append("</svg>")
    return "\n".join(out)


def render_markdown(meta, summaries, svg_name, raw_name):
    def ms(d, key):
        return f"{d[key]:.0f}" if d else "–"

    lines = [
        "# Kết quả đánh giá – perf (KT-13)",
        "",
        f"- Ngày chạy: {meta['startedAt']} · Commit: `{meta['commit']}` · Người chạy: {meta['runner']}",
        f"- Cấu hình: **LLM_MODE={meta['llmMode']}** (độ trễ LLM thật **chưa tính**, chỉ đo hạ tầng API + "
        "PostgreSQL + Redis) · model=fake · dữ liệu: tài khoản SV tạo riêng cho lần chạy, lớp mẫu `CTDL2026`",
        f"- Máy: {meta['machine']}",
        f"- Đích: `{meta['base']}` · kịch bản mỗi phiên: đăng nhập → tạo phiên → lời giảng → trả lời phản biện "
        f"tới COMPLETED → xem kết quả. Các phiên của một mức được thả cùng lúc. Timeout request {meta['timeoutS']} s.",
        "",
        f"![Biểu đồ hộp độ trễ và tỉ lệ lỗi theo số phiên]({svg_name})",
        "",
        "| Số phiên | Request | p50 (ms) | p95 (ms) | p99 (ms) | max (ms) | p50 / p95 bỏ đăng nhập (ms) | "
        "Lỗi request | Phiên lỗi | Phiên p50 (s) | Phiên p95 (s) | Thông lượng (req/s) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summaries:
        lat, ses = s["latencyMs"], s["sessionMs"]
        lines.append(
            f"| {s['level']} | {s['requests']} | {ms(lat, 'p50')} | {ms(lat, 'p95')} | {ms(lat, 'p99')} | "
            f"{ms(lat, 'max')} | {ms(s['latencyNoLoginMs'], 'p50')} / {ms(s['latencyNoLoginMs'], 'p95')} | "
            f"{s['requestErrors']} ({_pct(s['requestErrorRate'])}) | "
            f"{s['sessionErrors']}/{s['sessions']} ({_pct(s['sessionErrorRate'])}) | "
            f"{(ses['p50'] / 1000 if ses else 0):.2f} | {(ses['p95'] / 1000 if ses else 0):.2f} | "
            f"{s['throughputRps']:.1f} |"
        )
    lines += [
        "",
        "Chỉ tiêu Bảng 7.3: p95 ≤ 5 s. "
        + ", ".join(
            f"{s['level']} phiên: {'Đạt' if s['latencyMs'] and s['latencyMs']['p95'] <= 5000 else 'Chưa đạt'}"
            for s in summaries
        )
        + " (chỉ hạ tầng, LLM fake).",
        "",
        "## Theo endpoint (p50 / p95 ms, số lỗi)",
        "",
        "| Số phiên | Endpoint | Số request | p50 | p95 | Lỗi |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for s in summaries:
        for name, e in sorted(s["byEndpoint"].items()):
            p50 = f"{e['p50']:.0f}" if e["p50"] is not None else "–"
            p95 = f"{e['p95']:.0f}" if e["p95"] is not None else "–"
            lines.append(f"| {s['level']} | `{name}` | {e['count']} | {p50} | {p95} | {e['errors']} |")
    lines += ["", "## Lỗi gặp", ""]
    any_err = False
    for s in summaries:
        for kind, n in s["errorsByKind"].items():
            any_err = True
            lines.append(f"- {s['level']} phiên: `{kind}` × {n}")
    if not any_err:
        lines.append("- Không có phiên lỗi.")
    lines += ["", f"Số liệu thô: [`{raw_name}`]({raw_name}). Chạy lại: xem đầu `evals/perf/load_sessions.py`.", ""]
    return "\n".join(lines)


# ------------------------------------------------------------------ gọi API


class ApiError(RuntimeError):
    """Lỗi chuẩn bị dữ liệu; không chứa token / mật khẩu."""


async def call(client, method, path, endpoint, records, token=None, **kwargs):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    t0 = time.perf_counter()
    try:
        r = await client.request(method, path, headers=headers, **kwargs)
    except Exception as exc:  # timeout, mất kết nối… – ghi lại thành lỗi, không nuốt im lặng
        records.append(RequestRecord(endpoint, 0, (time.perf_counter() - t0) * 1000, type(exc).__name__))
        return None, f"{endpoint}: {type(exc).__name__}"
    ms = (time.perf_counter() - t0) * 1000
    rec = RequestRecord(endpoint, r.status_code, ms)
    records.append(rec)
    if rec.failed:
        try:
            code = r.json().get("error", {}).get("code", "UNKNOWN")
        except ValueError:
            code = "NON_JSON"
        return None, f"{endpoint}: HTTP {r.status_code} {code}"
    return r.json() if r.content else {}, None


async def prep(client, method, path, token=None, ok=(200, 201, 204), **kwargs):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = await client.request(method, path, headers=headers, **kwargs)
    if r.status_code not in ok:
        try:
            code = r.json().get("error", {}).get("code", "UNKNOWN")
        except ValueError:
            code = "NON_JSON"
        raise ApiError(f"{method} {path}: HTTP {r.status_code} {code}")
    return r.json() if r.content else {}


async def login(client, email, password):
    return (await prep(client, "POST", "/api/v1/auth/login", json={"email": email, "password": password}))[
        "accessToken"
    ]


async def ensure_published_tree(client, teacher, class_id):
    tree = await prep(client, "GET", f"/api/v1/classes/{class_id}/tree?draft=true", teacher)
    if tree["status"] == "PUBLISHED":
        return
    for node in tree["nodes"]:
        rubric = node.get("rubric")
        if rubric and rubric.get("approved"):
            continue
        rubric = (
            dict(rubric)
            if rubric
            else {
                "keyPoints": [{"id": "KP1", "content": f"Minh họa khái niệm {node['title']}", "isRequired": True}],
                "minChallenges": 3,
                "minPassedChallenges": 2,
                "passThreshold": 70,
                "scenarios": [],
                "misconceptions": [],
                "sourcePages": [],
            }
        )
        rubric["approved"] = True
        await prep(client, "PUT", f"/api/v1/nodes/{node['id']}/rubric", teacher, json=rubric)
    await prep(client, "POST", f"/api/v1/tree-versions/{tree['id']}/publish", teacher)


async def create_students(client, admin, tag, level, n, join_code):
    sem = asyncio.Semaphore(10)

    async def one(i):
        email = f"tai{tag}-{level}-{i:03d}@whybi.test"
        async with sem:
            created = await prep(
                client,
                "POST",
                "/api/v1/admin/users",
                admin,
                json={
                    "fullName": f"SV tải {level}-{i:03d}",
                    "email": email,
                    "role": "STUDENT",
                    "studentCode": f"T{tag}{level:03d}{i:03d}"[:20],
                    "cohort": "KT13",
                },
            )
            token = await login(client, email, created["password"])
            await prep(client, "POST", "/api/v1/classes/join", token, ok=(200, 201, 409), json={"joinCode": join_code})
            return {"email": email, "password": created["password"]}

    return await asyncio.gather(*(one(i) for i in range(n)))


async def run_session(client, index, account, node_id, start, text):
    recs = []
    await start.wait()
    t0 = time.perf_counter()

    def done(completed, turns, error=None):
        return SessionRecord(index, completed, (time.perf_counter() - t0) * 1000, turns, recs, error)

    body, err = await call(
        client,
        "POST",
        "/api/v1/auth/login",
        LOGIN,
        recs,
        json={"email": account["email"], "password": account["password"]},
    )
    if err or body is None:
        return done(False, 0, err)
    token = body["accessToken"]
    body, err = await call(
        client,
        "POST",
        "/api/v1/sessions",
        "POST /sessions",
        recs,
        token,
        json={"nodeId": node_id, "inputMode": "TEXT", "ttsEnabled": False},
    )
    if err or body is None:
        return done(False, 0, err)
    sid, status = body["sessionId"], body["status"]
    turns = 0
    while status != "COMPLETED":
        if status not in ("EXPLAINING", "CHALLENGING"):
            return done(False, turns, f"phiên kết thúc bất thường: {status}")
        if turns >= MAX_TURNS:
            return done(False, turns, f"vượt {MAX_TURNS} lượt")
        body, err = await call(
            client,
            "POST",
            f"/api/v1/sessions/{sid}/turns",
            "POST /sessions/{id}/turns",
            recs,
            token,
            json={"turnType": "EXPLANATION" if status == "EXPLAINING" else "ANSWER", "inputMode": "TEXT", "text": text},
        )
        turns += 1
        if err or body is None:
            return done(False, turns, err)
        status = body["status"]
    _, err = await call(client, "GET", f"/api/v1/sessions/{sid}/result", "GET /sessions/{id}/result", recs, token)
    return done(err is None, turns, err)


async def run_level(base, accounts, node_id, timeout, text):
    import httpx

    limits = httpx.Limits(max_connections=len(accounts) + 10, max_keepalive_connections=len(accounts) + 10)
    async with httpx.AsyncClient(base_url=base, timeout=timeout, limits=limits) as client:
        start = asyncio.Event()
        tasks = [asyncio.create_task(run_session(client, i, a, node_id, start, text)) for i, a in enumerate(accounts)]
        await asyncio.sleep(0.2)  # mọi task đã tới rào
        t0 = time.perf_counter()
        start.set()
        sessions = await asyncio.gather(*tasks)
        return sessions, (time.perf_counter() - t0) * 1000


def machine_info():
    info = f"{platform.system()} {platform.release()}, {platform.processor() or platform.machine()}, "
    info += f"{os.cpu_count()} luồng CPU"
    try:
        out = subprocess.run(
            ["docker", "info", "--format", "{{.NCPU}} {{.MemTotal}} {{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        ).stdout.split()
        info += f"; Docker {out[2]} cấp {out[0]} CPU, {int(out[1]) / 2**30:.1f} GiB RAM"
    except (OSError, subprocess.SubprocessError, IndexError, ValueError) as exc:
        info += f"; không đọc được docker info ({type(exc).__name__})"
    return info


def git_commit():
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT, check=True
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "?"


async def main_async(args):
    import httpx

    base = args.base.rstrip("/")
    tag = args.tag or datetime.now(UTC).strftime("%m%d%H%M")
    async with httpx.AsyncClient(base_url=base, timeout=args.timeout) as client:
        health = await client.get("/health")
        health.raise_for_status()
        admin = await login(client, args.admin, args.seed_password)
        teacher = await login(client, args.lecturer, args.seed_password)
        classes = await prep(client, "GET", "/api/v1/classes", teacher)
        matches = [c for c in classes if c["joinCode"] == args.join_code]
        if len(matches) != 1:
            raise ApiError("Không thấy lớp mẫu; chạy scripts/seed_db.py trước")
        class_id = matches[0]["id"]
        await ensure_published_tree(client, teacher, class_id)
        accounts_by_level = {}
        for level in args.levels:
            print(f"Chuẩn bị {level} SV…", flush=True)
            accounts_by_level[level] = await create_students(client, admin, tag, level, level, args.join_code)
        probe = await login(
            client, accounts_by_level[args.levels[0]][0]["email"], accounts_by_level[args.levels[0]][0]["password"]
        )
        my_map = await prep(client, "GET", f"/api/v1/classes/{class_id}/my-map", probe)
        nodes = {n["id"]: n for n in my_map["tree"]["nodes"]}
        startable = [c for c in my_map["progress"] if c["state"] == "AVAILABLE" and c.get("canStart", True)]
        if not startable:
            raise ApiError("Không có nút AVAILABLE cho SV mới")
        node = nodes[startable[0]["nodeId"]]
        points = (node.get("rubric") or {}).get("keyPoints", [])
        text = " ".join(p["content"] for p in points) or f"Mình giải thích về {node['title']}."

    meta = {
        "startedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": git_commit(),
        "runner": args.runner,
        "llmMode": args.llm_mode,
        "machine": machine_info(),
        "base": base,
        "timeoutS": args.timeout,
        "node": {"id": node["id"], "code": node.get("code"), "title": node["title"]},
        "levels": args.levels,
    }
    summaries, raw = [], {}
    for level in args.levels:
        if args.pause:
            await asyncio.sleep(args.pause)
        print(f"Chạy {level} phiên đồng thời…", flush=True)
        sessions, wall = await run_level(base, accounts_by_level[level], node["id"], args.timeout, text)
        s = summarize(level, sessions, wall)
        summaries.append(s)
        raw[str(level)] = [asdict(x) for x in sessions]
        lat = s["latencyMs"] or {}
        print(
            f"  p50={lat.get('p50', 0):.0f} ms p95={lat.get('p95', 0):.0f} ms "
            f"lỗi request={_pct(s['requestErrorRate'])} phiên lỗi={s['sessionErrors']}/{level}",
            flush=True,
        )

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    svg_name, raw_name = "perf_box.svg", "perf_raw.json"
    box_input = {
        s["level"]: {
            "values": [
                r["latency_ms"]
                for x in raw[str(s["level"])]
                for r in x["requests"]
                if not (r["error"] or r["status"] == 0 or r["status"] >= 400)
            ],
            "requestErrorRate": s["requestErrorRate"],
            "sessionErrorRate": s["sessionErrorRate"],
        }
        for s in summaries
    }
    title = f"KT-13 – độ trễ và tỉ lệ lỗi theo số phiên đồng thời (LLM_MODE={args.llm_mode})"
    (out / svg_name).write_text(render_svg(box_input, title), encoding="utf-8", newline="\n")
    (out / raw_name).write_text(
        json.dumps({"meta": meta, "summaries": summaries, "sessions": raw}, ensure_ascii=False, indent=1),
        encoding="utf-8",
        newline="\n",
    )
    (out / "perf.md").write_text(render_markdown(meta, summaries, svg_name, raw_name), encoding="utf-8", newline="\n")
    print(f"Đã ghi {out / 'perf.md'}, {svg_name}, {raw_name}")
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # console Windows mặc định cp125x không in được tiếng Việt
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", default="http://localhost")
    p.add_argument("--levels", default="20,50,100", type=lambda s: [int(x) for x in s.split(",")])
    p.add_argument("--timeout", type=float, default=60.0, help="giây cho mỗi request")
    p.add_argument("--pause", type=float, default=5.0, help="nghỉ giữa các mức (giây)")
    p.add_argument("--tag", default="", help="hậu tố email tài khoản tải (mặc định theo giờ UTC)")
    p.add_argument("--admin", default="admin@whybi.test")
    p.add_argument("--lecturer", default="gv@whybi.test")
    p.add_argument("--join-code", default="CTDL2026")
    p.add_argument(
        "--seed-password",
        default=os.environ.get("LOAD_SEED_PASSWORD", SEED_PASSWORD),
        help="mật khẩu QTV/GV (mặc định seed dev; môi trường khác đặt LOAD_SEED_PASSWORD)",
    )
    p.add_argument("--llm-mode", default="fake", help="ghi vào báo cáo; phải khớp LLM_MODE của backend")
    p.add_argument("--runner", default="Quyền (KT)")
    p.add_argument("--out-dir", default=str(ROOT / "evals" / "results"))
    args = p.parse_args(argv)
    try:
        return asyncio.run(main_async(args))
    except ApiError as exc:
        print(f"Lỗi chuẩn bị: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
