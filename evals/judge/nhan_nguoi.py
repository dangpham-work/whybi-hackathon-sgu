"""Gán nhãn người cho bộ lời giảng Judge (tiêu chí III.4 – nhãn phải do người, độc lập, có đo đồng thuận).

Quy trình:
  1. xuat  – mỗi người một phiếu CSV mù (không thấy nhãn cũ / nhãn người kia, thứ tự xáo riêng).
  2. Hai người điền cột `nhan` (Đạt / Chưa đạt) và 5 cột điểm 0–100, độc lập.
  3. nhap  – đo Cohen's κ giữa 2 người, xuất `tranh_chap.csv` cho các mẫu lệch nhãn.
  4. Hai người thảo luận, điền cột `chot` trong `tranh_chap.csv`, chạy lại `nhap --chot … --ghi`
     → ghi `labeled.jsonl` với source="human" (điểm = trung bình 2 người).

Chạy (từ thư mục backend/):
  uv run python ../evals/judge/nhan_nguoi.py xuat --nguoi Quyen
  uv run python ../evals/judge/nhan_nguoi.py nhap ../evals/judge/phieu/Quyen.csv ../evals/judge/phieu/Thang.csv
  uv run python ../evals/judge/nhan_nguoi.py nhap A.csv B.csv --chot ../evals/judge/phieu/tranh_chap.csv --ghi
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import unicodedata
from pathlib import Path

DIR = Path(__file__).resolve().parent
EVALS = DIR.parent
ROOT = EVALS.parent
sys.path.insert(0, str(EVALS))

from metrics import cohen_kappa  # noqa: E402

TIEU_CHI = ["CORRECTNESS", "COVERAGE", "ESSENCE", "ROBUSTNESS", "CLARITY"]
COT_PHIEU = ["id", "node", "ten_nut", "y_bat_buoc", "loi_giang", "nhan", *TIEU_CHI, "ghi_chu"]
COT_TRANH_CHAP = ["id", "loi_giang", "nhan_a", "nhan_b", "chot"]

_DAT = {"đạt", "dat", "d", "pass", "passed"}
_CHUA_DAT = {"chưa đạt", "chua dat", "không đạt", "khong dat", "c", "fail", "failed"}
_HIEN_THI = {"PASSED": "Đạt", "FAILED": "Chưa đạt"}


def _chuan_nhan(raw: str) -> str | None:
    s = unicodedata.normalize("NFC", (raw or "").strip().lower())
    if s in _DAT:
        return "PASSED"
    if s in _CHUA_DAT:
        return "FAILED"
    return None


def _y_bat_buoc(node: dict) -> str:
    kps = (node.get("rubric") or {}).get("keyPoints") or []
    return " | ".join(f"{kp['id']}: {kp['content']}" + (" (bắt buộc)" if kp.get("isRequired") else "") for kp in kps)


def xuat_phieu(mau: list[dict], cay: dict, nguoi: str, out_dir: Path) -> Path:
    """Phiếu mù cho một người: chỉ có lời giảng + ý của rubric, không nhãn cũ; thứ tự xáo cố định theo tên."""
    nodes = {n["code"]: n for n in cay.get("nodes", [])}
    rows = list(mau)
    random.Random(f"phieu:{nguoi}").shuffle(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{nguoi}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:  # BOM để Excel / Google Sheets đọc đúng tiếng Việt
        w = csv.DictWriter(f, fieldnames=COT_PHIEU)
        w.writeheader()
        for m in rows:
            node = nodes.get(m["node"], {})
            w.writerow(
                {
                    "id": m["id"],
                    "node": m["node"],
                    "ten_nut": node.get("title", ""),
                    "y_bat_buoc": _y_bat_buoc(node),
                    "loi_giang": m["transcript"],
                }
            )
    return path


def doc_phieu(path: Path) -> dict[str, dict]:
    """{id: {"label", "scores"}}; dòng thiếu / sai báo lỗi kèm `<file>:<dòng>` (dòng 1 là tiêu đề)."""
    out: dict[str, dict] = {}
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            vi_tri = f"{Path(path).name}:{i}"
            id_ = (row.get("id") or "").strip()
            label = _chuan_nhan(row.get("nhan", ""))
            if label is None:
                raise ValueError(f"{vi_tri}: cột nhan phải là 'Đạt' hoặc 'Chưa đạt', đang là {row.get('nhan')!r}")
            scores = {}
            for tc in TIEU_CHI:
                raw = (row.get(tc) or "").strip()
                try:
                    v = int(float(raw))
                except ValueError:
                    raise ValueError(f"{vi_tri}: cột {tc} phải là số 0–100, đang là {raw!r}") from None
                if not 0 <= v <= 100:
                    raise ValueError(f"{vi_tri}: cột {tc} = {v} ngoài khoảng 0–100")
                scores[tc] = v
            if id_ in out:
                raise ValueError(f"{vi_tri}: trùng id {id_}")
            out[id_] = {"label": label, "scores": scores, "ghi_chu": (row.get("ghi_chu") or "").strip()}
    return out


def doi_chieu(a: dict[str, dict], b: dict[str, dict]) -> tuple[float, list[str]]:
    """Cohen's κ nhãn Đạt/Chưa đạt giữa 2 người và danh sách id lệch nhãn."""
    if set(a) != set(b):
        lech = sorted(set(a) ^ set(b))
        raise ValueError(f"hai phiếu không cùng tập lời giảng, lệch: {', '.join(lech)}")
    ids = sorted(a)
    kappa = cohen_kappa([a[i]["label"] for i in ids], [b[i]["label"] for i in ids])
    return kappa, [i for i in ids if a[i]["label"] != b[i]["label"]]


def gop(mau: list[dict], a: dict, b: dict, ten_a: str, ten_b: str, chot: dict[str, str]) -> list[dict]:
    """Bản ghi labeled.jsonl từ 2 phiếu người. Mọi mẫu lệch nhãn phải có nhãn chốt."""
    _, tranh_chap = doi_chieu(a, b)
    chua_chot = [i for i in tranh_chap if i not in chot]
    if chua_chot:
        raise ValueError(f"chưa có nhãn chốt cho: {', '.join(chua_chot)}")
    out = []
    for m in mau:
        id_ = m["id"]
        ra, rb = a[id_], b[id_]
        rec = {
            "id": id_,
            "node": m["node"],
            "transcript": m["transcript"],
            "label": chot.get(id_, ra["label"]) if id_ in tranh_chap else ra["label"],
            "scores": {tc: int((ra["scores"][tc] + rb["scores"][tc]) / 2 + 0.5) for tc in TIEU_CHI},
            "annotator": f"{ten_a} & {ten_b}",
            "source": "human",
        }
        if id_ in tranh_chap:
            rec["note"] = (
                f"tranh chấp {ten_a}: {_HIEN_THI[ra['label']]} / {ten_b}: {_HIEN_THI[rb['label']]}"
                f" → chốt {_HIEN_THI[rec['label']]}"
            )
        out.append(rec)
    return out


def _doc_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _doc_chot(path: Path) -> dict[str, str]:
    chot = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            if not (row.get("chot") or "").strip():
                continue
            label = _chuan_nhan(row["chot"])
            if label is None:
                raise ValueError(f"{path.name}:{i}: cột chot phải là 'Đạt' hoặc 'Chưa đạt'")
            chot[row["id"].strip()] = label
    return chot


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="lenh", required=True)
    x = sub.add_parser("xuat", help="xuất phiếu mù cho một người")
    x.add_argument("--nguoi", required=True, help="tên người gán nhãn, không dấu cách (vd. Quyen)")
    x.add_argument("--ra", type=Path, default=DIR / "phieu")
    n = sub.add_parser("nhap", help="đo κ giữa 2 phiếu, gộp nhãn chốt")
    n.add_argument("phieu_a", type=Path)
    n.add_argument("phieu_b", type=Path)
    n.add_argument("--chot", type=Path, help="tranh_chap.csv đã điền cột chot")
    n.add_argument("--ghi", action="store_true", help="ghi đè labeled.jsonl khi đã chốt đủ")
    args = ap.parse_args(argv)

    labeled = DIR / "labeled.jsonl"
    mau = _doc_jsonl(labeled)
    if args.lenh == "xuat":
        cay = json.loads((ROOT / "seed" / "tree_ctdl_gt.json").read_text(encoding="utf-8"))
        path = xuat_phieu(mau, cay, args.nguoi, args.ra)
        print(f"Đã xuất {len(mau)} lời giảng → {path}")
        return 0

    a, b = doc_phieu(args.phieu_a), doc_phieu(args.phieu_b)
    ten_a, ten_b = args.phieu_a.stem, args.phieu_b.stem
    kappa, tranh_chap = doi_chieu(a, b)
    print(f"Đồng thuận giữa {ten_a} và {ten_b}: κ = {kappa:.3f} · lệch nhãn {len(tranh_chap)}/{len(a)}")
    chot = _doc_chot(args.chot) if args.chot else {}
    if not args.chot and tranh_chap:
        path = args.phieu_a.parent / "tranh_chap.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COT_TRANH_CHAP)
            w.writeheader()
            by_id = {m["id"]: m for m in mau}
            for i in tranh_chap:
                w.writerow(
                    {
                        "id": i,
                        "loi_giang": by_id[i]["transcript"],
                        "nhan_a": f"{ten_a}: {_HIEN_THI[a[i]['label']]}",
                        "nhan_b": f"{ten_b}: {_HIEN_THI[b[i]['label']]}",
                    }
                )
        print(f"Thảo luận rồi điền cột 'chot' trong {path}, sau đó chạy lại với --chot {path} --ghi")
    if not args.ghi:
        return 0
    try:
        recs = gop(mau, a, b, ten_a, ten_b, chot)
    except ValueError as e:
        print(f"Chưa ghi: {e}", file=sys.stderr)
        return 1
    labeled.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")
    print(f"Đã ghi {len(recs)} nhãn người → {labeled} (κ giữa 2 người = {kappa:.3f}, ghi số này vào results/judge.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
