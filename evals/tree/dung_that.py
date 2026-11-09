"""Đo dựng cây thật bằng AI trên PDF thật – độ dày cạnh, nút trùng, số lượt gọi. Tốn token (LLM thật).

Chạy từ gốc repo, backend đã `uv sync`, `.env` có khóa (LLM_MODE=real):
    cd backend && PYTHONPATH=. uv run python ../evals/tree/dung_that.py <giaotrinh.pdf> [số_đoạn=6] [DETAIL=STANDARD]

Lấy N đoạn đầu kể từ chương 1 của giáo trình (bỏ trang mục lục), dựng cây rồi in một dòng Markdown:
nút, cạnh thô (AI trả), cạnh sau rút gọn bắc cầu, cạnh/nút, cặp nút trùng tên, lượt call_json / embed, giây.
So hai bản mã (trước / sau thay đổi) bằng cách chạy cùng lệnh trên hai checkout, chú ý cùng tham số.
Không thay cho `evaluate.py` (đo P/R/F1 so với cây chuẩn); đây chỉ đo hình dạng cây và chi phí.
"""

import re
import sys
import time
import unicodedata
from dataclasses import asdict

import networkx as nx
import pymupdf

from app.ai.agents.tree_builder import TreeBuilder, split_chapters
from app.ai.gateway import get_gateway
from app.algorithms.dag import sanitize
from app.services.syllabus_toc import DETAIL_CAPS, find_toc
from app.workers.documents import extract_pdf


class NoOcr:
    def image_to_text(self, png: bytes) -> str:
        return ""


class Counting:
    """Bọc gateway để đếm lượt gọi."""

    def __init__(self, gw):
        self.gw, self.calls, self.embeds = gw, 0, 0

    def call_json(self, *a, **k):
        self.calls += 1
        return self.gw.call_json(*a, **k)

    def embed(self, texts):
        self.embeds += 1
        return self.gw.embed(texts)

    def __getattr__(self, name):
        return getattr(self.gw, name)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", unicodedata.normalize("NFC", s).casefold())).strip()


def main(path: str, n_chunks: int = 6, detail: str = "STANDARD") -> None:
    data = open(path, "rb").read()
    pages = [asdict(p) for p in extract_pdf(data, NoOcr())]
    with pymupdf.open(stream=data, filetype="pdf") as d:
        marks = [(a, b, c) for a, b, c in (x[:3] for x in d.get_toc())]
    res = find_toc(pages, marks)
    skip = set(res.toc_pages)
    start = res.entries[0].start if res.entries else 1
    body = [p for p in pages if p["number"] >= start and p["number"] not in skip]
    sel = []
    for p in body:
        sel.append(p)
        if len(split_chapters(sel)) >= n_chunks:
            break
    chunks = len(split_chapters(sel))

    gw = Counting(get_gateway())
    t0 = time.time()
    tree = TreeBuilder(gw, max_concepts=DETAIL_CAPS[detail]).build(sel)
    secs = time.time() - t0

    g = nx.DiGraph()
    g.add_nodes_from(n.key for n in tree.nodes)
    g.add_edges_from((e.from_key, e.to_key, {"confidence": e.confidence, "source": e.source}) for e in tree.edges)
    dag, _, removed = sanitize(g)
    names: dict[str, int] = {}
    for n in tree.nodes:
        names[norm(n.title)] = names.get(norm(n.title), 0) + 1
    dup = sum(v - 1 for v in names.values() if v > 1)
    n = max(1, len(tree.nodes))
    print(
        f"| {path.split('/')[-1][:28]} | {chunks} | {detail} | {len(tree.nodes)} | {len(tree.edges)} | "
        f"{dag.number_of_edges()} | {dag.number_of_edges() / n:.2f} | {dup} | {gw.calls} | {gw.embeds} | {secs:.0f} |"
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 6, sys.argv[3] if len(sys.argv) > 3 else "STANDARD")
