"""Tạo GitHub Issue từ docs/cards/*.md (một thẻ = một issue). Cần `gh auth login` và đã chạy setup_labels.sh.

python scripts/create_issues.py --dry-run          # xem trước
python scripts/create_issues.py --only C1          # chỉ thẻ C1
python scripts/create_issues.py                    # tạo thật (bỏ qua thẻ đã có issue cùng tiêu đề)
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

CARDS = Path(__file__).resolve().parent.parent / "docs" / "cards"


def parse_cards() -> list[dict]:
    cards = []
    for f in sorted(CARDS.glob("*.md")):
        if f.name == "README.md":
            continue
        for block in re.split(r"^## ", f.read_text(encoding="utf-8"), flags=re.M)[1:]:
            cid, body = block.split("\n", 1)
            fields = dict(re.findall(r"^- \*\*(.+?):\*\* (.*)$", body, flags=re.M))
            cards.append({"id": cid.strip(), "body": body.strip(), **fields})
    return cards


def existing_titles() -> set[str]:
    out = subprocess.run(
        ["gh", "issue", "list", "--state", "all", "--limit", "500", "--json", "title"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    return {i["title"] for i in json.loads(out)}


sys.stdout.reconfigure(encoding="utf-8")  # console Windows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", help="Tiền tố mã thẻ, vd. C1, GD, KT-0")
    args = ap.parse_args()

    cards = [c for c in parse_cards() if not args.only or c["id"].startswith(args.only)]
    have = set() if args.dry_run else existing_titles()
    for c in cards:
        task = c.get("Thẻ việc", "")
        title = f"{c['id']} – {task[:80]}{'…' if len(task) > 80 else ''}"
        rnd = re.search(r"\d", c.get("Vòng", "1"))
        labels = ["card", c["id"].split("-")[0], f"vong-{rnd.group() if rnd else 1}"]
        if any(t.startswith(c["id"] + " ") for t in have):
            print(f"= bỏ qua {c['id']} (đã có)")
            continue
        if args.dry_run:
            print(f"+ {title}  [{', '.join(labels)}]")
            continue
        label_args = [arg for lb in labels for arg in ("--label", lb)]
        subprocess.run(["gh", "issue", "create", "--title", title, "--body", c["body"], *label_args], check=True)
    print(f"{len(cards)} thẻ")


if __name__ == "__main__":
    main()
