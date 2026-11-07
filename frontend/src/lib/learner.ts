/**
 * Dữ liệu màn SV-02 Bản đồ học tập / SV-03 Chi tiết nút (GD-06) dựng từ `MyMap` – hợp đồng C2-10
 * (backend/app/models/schemas/mastery.py: MyMap, NodeProgress; GET /classes/{classId}/my-map).
 * Chỉ đọc dữ liệu máy chủ trả, không tự suy trạng thái thành thạo (MasteryService là nơi duy nhất quyết định).
 */
import type { Schema } from "./api";
import { MASTERY } from "./status";

export type MyMap = Schema<"MyMap">;
export type NodeProgress = Schema<"NodeProgress">;
export type TreeNode = Schema<"Node">;

export interface LearnerItem {
  node: TreeNode;
  progress: NodeProgress;
  /** Nút nằm trong `frontier` – nên học tiếp (mục 2.2.1). */
  frontier: boolean;
}

export interface LearnerView {
  /** Nút theo thứ tự tiên quyết (tiên quyết luôn đứng trước), cùng tầng giữ thứ tự của cây. */
  items: LearnerItem[];
  byKey: Map<string, LearnerItem>;
  map: MyMap;
}

/** Nút có trong cây nhưng máy chủ không trả ô ma trận → coi là Khóa, không cho bắt đầu. */
const lockedFor = (node: TreeNode): NodeProgress => ({
  nodeId: node.id ?? node.key,
  nodeKey: node.key,
  state: "LOCKED",
  attempts: 0,
  missingPrerequisites: [],
  canStart: false,
});

/** Sắp xếp topo (Kahn) ổn định theo thứ tự nút trong cây. Cây luôn là DAG (BR-01) – nút còn sót (nếu có) nối vào cuối. */
function topoOrder(nodes: TreeNode[], edges: Schema<"Edge">[]): TreeNode[] {
  const index = new Map(nodes.map((n, i) => [n.key, i]));
  const indeg = new Map(nodes.map((n) => [n.key, 0]));
  const next = new Map<string, string[]>();
  for (const e of edges) {
    if (!index.has(e.fromKey) || !index.has(e.toKey)) continue;
    indeg.set(e.toKey, indeg.get(e.toKey)! + 1);
    next.set(e.fromKey, [...(next.get(e.fromKey) ?? []), e.toKey]);
  }
  const ready = nodes.filter((n) => indeg.get(n.key) === 0).map((n) => n.key);
  const out: string[] = [];
  while (ready.length) {
    ready.sort((a, b) => index.get(a)! - index.get(b)!);
    const k = ready.shift()!;
    out.push(k);
    for (const t of next.get(k) ?? []) {
      indeg.set(t, indeg.get(t)! - 1);
      if (indeg.get(t) === 0) ready.push(t);
    }
  }
  const seen = new Set(out);
  return [...out.map((k) => nodes[index.get(k)!]), ...nodes.filter((n) => !seen.has(n.key))];
}

export function learnerView(map: MyMap): LearnerView {
  const progress = new Map(map.progress.map((p) => [p.nodeKey, p]));
  const frontier = new Set(map.frontier);
  const items = topoOrder(map.tree.nodes, map.tree.edges).map((node) => ({
    node,
    progress: progress.get(node.key) ?? lockedFor(node),
    frontier: frontier.has(node.key),
  }));
  return { items, byKey: new Map(items.map((i) => [i.node.key, i])), map };
}

export const nodeName = (n: TreeNode) => (n.code ? `${n.code} ${n.title}` : n.title);
const score = (s: number) => `${Math.round(s)}/100`;
const pad = (n: number) => String(n).padStart(2, "0");
/** "18/09" theo giờ máy SV (tự định dạng – ICU của các môi trường cho dấu phân cách khác nhau). */
const shortDate = (iso: string) => {
  const d = new Date(iso);
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}`;
};
export const clock = (iso: string) => {
  const d = new Date(iso);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
};
/** `retryAt` còn ở tương lai (BR-11 – chờ 10 phút sau lần Chưa đạt). */
export const waitingRetry = (p: NodeProgress, now = Date.now()) => !!p.retryAt && new Date(p.retryAt).getTime() > now;

/** Tên ngắn của các tiên quyết còn thiếu ("N5, N6"); key lạ thì giữ nguyên key. */
export const missingNames = (p: NodeProgress, byKey: Map<string, LearnerItem>) =>
  p.missingPrerequisites.map((k) => byKey.get(k)?.node.code || byKey.get(k)?.node.title || k).join(", ");

/** Dòng phụ dưới tên nút (Figma SV-02) – luôn mở đầu bằng chữ trạng thái để không chỉ dựa vào màu (NFR-12). */
export function nodeDetail(p: NodeProgress, byKey: Map<string, LearnerItem>): string {
  const label = MASTERY[p.state].label;
  const best = p.bestScore != null ? `cao nhất ${score(p.bestScore)}` : null;
  switch (p.state) {
    case "MASTERED":
      return [p.bestScore != null ? `Đạt ${score(p.bestScore)}` : label, p.updatedAt && shortDate(p.updatedAt)].filter(Boolean).join(" · ");
    case "LOCKED":
      return p.missingPrerequisites.length ? `${label} · mở khi bạn Đạt ${missingNames(p, byKey)}` : label;
    case "AVAILABLE":
      return p.attempts === 0 ? `${label} · chưa thử` : [label, best, `${p.attempts} lượt`].filter(Boolean).join(" · ");
    case "NOT_PASSED":
    case "NEEDS_REVERIFY":
      return [label, best, p.attempts ? `${p.attempts} lượt` : null, waitingRetry(p) ? `thử lại lúc ${clock(p.retryAt!)}` : null]
        .filter(Boolean)
        .join(" · ");
    default:
      return label;
  }
}

/** Nút cho nút "Bắt đầu giảng" ở SV-02: nút đầu tiên trong frontier bắt đầu được ngay, nếu không thì nút đầu tiên canStart. */
export function nextToLearn(view: LearnerView): LearnerItem | null {
  return view.items.find((i) => i.frontier && i.progress.canStart) ?? view.items.find((i) => i.progress.canStart) ?? null;
}

/** Tiên quyết trực tiếp của nút (cạnh fromKey → key), theo thứ tự trong bản đồ. */
export function prerequisitesOf(key: string, view: LearnerView): LearnerItem[] {
  const from = new Set(view.map.tree.edges.filter((e) => e.toKey === key).map((e) => e.fromKey));
  return view.items.filter((i) => from.has(i.node.key));
}
