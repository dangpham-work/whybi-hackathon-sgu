"""KT-09: đo nút/cạnh có hướng bằng tên và alias đã chốt, không dùng LLM.

Mỗi gold nhận tối đa một prediction. Tên chuẩn được ưu tiên trước alias, rồi key
tăng dần, độc lập với thứ tự đầu vào và cạnh. Nút dự đoán dư vẫn là FP.
Mẫu số bằng 0 trả None, không diễn giải tập rỗng thành điểm hoàn hảo.
Các hàm chỉ tính số đo; không chứng nhận nguồn gold hoặc chất lượng model thật.
"""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from typing import TYPE_CHECKING

from app.algorithms.dag import build_graph, find_cycle
from app.models.schemas.tree import TreeVersion

if TYPE_CHECKING:
    from eval_datasets import GoldTree


def normalize_title(text: str) -> str:
    """Giữ dấu và toán tử; đồng nghĩa khác chỉ được khai báo trong gold.aliases."""
    if not isinstance(text, str):
        raise ValueError("title must be a nonempty string")
    normalized = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    if not normalized:
        raise ValueError("title must be a nonempty string")
    return normalized


def _validate_tree(tree: TreeVersion, label: str) -> TreeVersion:
    # Validate lại bằng dict: Pydantic có thể bỏ qua instance đã bị mutate.
    tree = TreeVersion.model_validate(tree.model_dump())
    for node in tree.nodes:
        normalize_title(node.title)
    edges = [(edge.from_key, edge.to_key) for edge in tree.edges]
    if len(edges) != len(set(edges)):
        raise ValueError(f"{label}: duplicate edge")
    if find_cycle(build_graph(tree)):
        raise ValueError(f"{label}: cycle")
    return tree


def _name_index(gold: GoldTree, tree: TreeVersion) -> tuple[dict[str, str], dict[str, str]]:
    titles = {node.key: normalize_title(node.title) for node in tree.nodes}
    if not isinstance(gold.aliases, dict) or set(gold.aliases) - set(titles):
        raise ValueError("gold aliases must reference existing nodes")
    index: dict[str, str] = {}
    for key, title in titles.items():
        aliases = gold.aliases.get(key, [])
        if not isinstance(aliases, list):
            raise ValueError("gold aliases must be lists of titles")
        for name in [title, *(normalize_title(alias) for alias in aliases)]:
            if name in index and index[name] != key:
                raise ValueError(f"ambiguous gold title or alias: {name}")
            index[name] = key
    return titles, index


def _counts(tp: int, fp: int, fn: int) -> dict:
    if any(type(count) is not int or count < 0 for count in (tp, fp, fn)):
        raise ValueError("counts must be nonnegative integers")
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
    }


def evaluate_tree(pred: TreeVersion, gold: GoldTree) -> dict:
    """So sánh cây sau hậu xử lý; từ chối đồ thị sai thay vì tự sửa để tăng điểm.

    `mapping` dùng pred_key → gold_key. Cạnh FP dùng key dự đoán, cạnh FN dùng
    key gold. Cạnh gắn với nút chưa khớp vẫn tính trong mẫu số precision.
    """
    pred = _validate_tree(pred, "prediction")
    truth = _validate_tree(gold.tree, "gold")
    gold_titles, names = _name_index(gold, truth)
    candidates: dict[str, list[tuple[bool, str]]] = defaultdict(list)
    for node in pred.nodes:
        title = normalize_title(node.title)
        if title in names:
            key = names[title]
            candidates[key].append((title != gold_titles[key], node.key))

    mapping: dict[str, str] = {}
    duplicates = []
    for key, options in sorted(candidates.items()):
        ranked = sorted(options)
        representative = ranked[0][1]
        mapping[representative] = key
        if len(ranked) > 1:
            duplicates.append(
                {
                    "gold_key": key,
                    "kept_predicted_key": representative,
                    "extra_predicted_keys": sorted(item[1] for item in ranked[1:]),
                }
            )
    mapping = dict(sorted(mapping.items()))
    gold_edges = {(edge.from_key, edge.to_key) for edge in truth.edges}
    matched_edges: set[tuple[str, str]] = set()
    extra_edges = []
    for edge in pred.edges:
        pair = (mapping.get(edge.from_key), mapping.get(edge.to_key))
        if pair in gold_edges:
            matched_edges.add(pair)
        else:
            extra_edges.append([edge.from_key, edge.to_key])
    return {
        "name": gold.name,
        "nodes": _counts(len(mapping), len(pred.nodes) - len(mapping), len(truth.nodes) - len(mapping)),
        "edges": _counts(len(matched_edges), len(extra_edges), len(gold_edges) - len(matched_edges)),
        "mapping": mapping,
        "unmatched_predicted_nodes": sorted({node.key for node in pred.nodes} - mapping.keys()),
        "unmatched_gold_nodes": sorted(set(gold_titles) - set(mapping.values())),
        "false_positive_edges": sorted(extra_edges),
        "false_negative_edges": [list(pair) for pair in sorted(gold_edges - matched_edges)],
        "duplicate_matches": duplicates,
    }


def aggregate(scores: list[dict]) -> dict:
    """Micro cộng số đếm; macro cho mỗi tài liệu một trọng số và nêu số mẫu xác định.

    Không nhận tỷ lệ đã ghi làm nguồn tin: tính lại từ tp/fp/fn. Người gọi phải giữ
    riêng các case lỗi/thiếu để không kết luận đạt từ một tập con thành công.
    """
    result: dict = {"cases": len(scores)}
    for kind in ("nodes", "edges"):
        rows = []
        for score in scores:
            try:
                counts = score[kind]
                rows.append(_counts(counts["tp"], counts["fp"], counts["fn"]))
            except (KeyError, TypeError) as exc:
                raise ValueError(f"missing {kind} counts") from exc
        macro: dict = {"defined": {}}
        for measure in ("precision", "recall", "f1"):
            values = [row[measure] for row in rows if row[measure] is not None]
            macro[measure] = sum(values) / len(values) if values else None
            macro["defined"][measure] = len(values)
        result[kind] = {
            "micro": _counts(*(sum(row[count] for row in rows) for count in ("tp", "fp", "fn"))),
            "macro": macro,
        }
    return result
