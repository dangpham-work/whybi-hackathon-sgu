/**
 * Tự sắp xếp cây kỹ năng (GD-03) bằng dagre (@dagrejs/dagre) – xếp tầng theo cạnh tiên quyết X → Y,
 * nên nút tiên quyết luôn nằm trên (TB) hoặc bên trái (LR) nút phụ thuộc.
 * Chọn dagre thay elkjs: chạy đồng bộ (test và render đơn giản), nhẹ, đủ cho cây ≤ 50 nút.
 */
import dagre from "@dagrejs/dagre";
import type { components } from "./api-types";

type TreeNode = components["schemas"]["Node"];
type TreeEdge = components["schemas"]["Edge"];

export const NODE_W = 220;
export const NODE_H = 64;

export type Direction = "TB" | "LR";
export interface Point {
  x: number;
  y: number;
}

/**
 * Vị trí góc trên-trái của từng nút theo `key`.
 * Mọi nút đều có positionX/Y (GV đã kéo thả và lưu ở GV-04) → dùng nguyên; thiếu một nút → dagre xếp lại cả cây.
 */
export function layoutTree(nodes: TreeNode[], edges: TreeEdge[], direction: Direction = "TB"): Map<string, Point> {
  const pos = new Map<string, Point>();
  if (nodes.length && nodes.every((n) => n.positionX != null && n.positionY != null)) {
    for (const n of nodes) pos.set(n.key, { x: n.positionX!, y: n.positionY! });
    return pos;
  }

  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: direction, nodesep: 32, ranksep: 56, marginx: 16, marginy: 16 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of nodes) g.setNode(n.key, { width: NODE_W, height: NODE_H });
  const keys = new Set(nodes.map((n) => n.key));
  for (const e of edges) if (keys.has(e.fromKey) && keys.has(e.toKey)) g.setEdge(e.fromKey, e.toKey);
  dagre.layout(g);

  for (const n of nodes) {
    const { x, y } = g.node(n.key); // dagre trả tâm nút
    pos.set(n.key, { x: x - NODE_W / 2, y: y - NODE_H / 2 });
  }
  return pos;
}
