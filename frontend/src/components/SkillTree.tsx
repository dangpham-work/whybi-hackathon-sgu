/**
 * SkillTree – vẽ DAG bằng React Flow, tự sắp xếp bằng dagre (lib/tree-layout.ts), tô màu theo trạng thái.
 * Dùng chung cho GV-04 (sửa kéo thả), GV-05 (bản đồ nhiệt), SV-02 (bản đồ học tập). Thẻ: GD-03 (Thắng).
 * Dữ liệu: Node / Edge camelCase sinh từ OpenAPI (`components["schemas"]` – backend/app/models/schemas/tree.py).
 * Màu trạng thái luôn kèm biểu tượng + chữ qua MASTERY / HEAT / ROOT_CAUSE (NFR-12).
 */
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  useNodesState,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo } from "react";
import type { components } from "../lib/api-types";
import { HEAT, MASTERY, ROOT_CAUSE, type HeatColor, type MasteryState } from "../lib/status";
import { layoutTree, NODE_H, NODE_W, type Direction } from "../lib/tree-layout";
import { StatusLegend } from "./StatusBadge";

export type TreeNode = components["schemas"]["Node"];
export type TreeEdge = components["schemas"]["Edge"];
type BloomLevel = components["schemas"]["BloomLevel"];

export const BLOOM_LABEL: Record<BloomLevel, string> = {
  REMEMBER: "Nhớ",
  UNDERSTAND: "Hiểu",
  APPLY: "Vận dụng",
  ANALYZE: "Phân tích",
  EVALUATE: "Đánh giá",
  CREATE: "Sáng tạo",
};

export interface SkillTreeProps {
  /** edit = GV-04 kéo thả / nối cạnh · heatmap = GV-05 · learner = SV-02 */
  mode: "edit" | "heatmap" | "learner";
  nodes: TreeNode[];
  edges: TreeEdge[];
  /** Trạng thái thành thạo theo `key` (SV-02, GV-04). Thiếu key ở chế độ learner → coi là Khóa. */
  mastery?: Record<string, MasteryState>;
  /** Màu bản đồ nhiệt theo `key` (GV-05). Thiếu key → Chưa đủ mẫu. */
  heat?: Record<string, HeatColor>;
  /** Dòng phụ theo `key`, vd. "Đạt 92/100 · 18/09", "32% Đạt · 25 SV thử". Mặc định: Chương · Bloom. */
  details?: Record<string, string>;
  /** Nút được RootCauseAnalyzer đánh dấu điểm nghẽn gốc (◎ GỐC). */
  rootCauseKey?: string | null;
  selectedKey?: string | null;
  direction?: Direction;
  /** Chiều cao khung vẽ (px hoặc CSS). */
  height?: number | string;
  legend?: boolean;
  onNodeClick?: (node: TreeNode) => void;
  /** Chỉ ở mode="edit": GV thả nút xong → lưu positionX/Y. */
  onNodeMove?: (key: string, pos: { x: number; y: number }) => void;
  /** Chỉ ở mode="edit": GV kéo từ mép nút để tạo cạnh tiên quyết from → to (backend chặn chu trình – BR-01). */
  onConnect?: (fromKey: string, toKey: string) => void;
}

interface Look {
  label: string;
  icon: (typeof MASTERY)[MasteryState]["icon"];
  className: string;
}

type SkillNodeData = {
  node: TreeNode;
  look: Look | null;
  detail: string;
  root: boolean;
  selected: boolean;
  editable: boolean;
  vertical: boolean;
};
type SkillFlowNode = Node<SkillNodeData, "skill">;

const NEUTRAL = "bg-surface text-ink-900 border-line-strong";

function SkillNodeView({ data }: NodeProps<SkillFlowNode>) {
  const { node, look, detail, root, selected, editable, vertical } = data;
  const Icon = look?.icon;
  const RootIcon = ROOT_CAUSE.icon;
  const name = `${node.code ? `${node.code} ` : ""}${node.title}`;
  const handleCls = editable ? "!size-2.5 !border-surface !bg-teal" : "!opacity-0 !pointer-events-none";
  return (
    <div
      aria-label={look ? `${name} – ${look.label}` : name}
      style={{ width: NODE_W, height: NODE_H }}
      className={`flex cursor-pointer flex-col justify-center gap-0.5 rounded-md border px-3 shadow-card ${look?.className ?? NEUTRAL} ${
        root ? "border-2 !border-ink-900" : ""
      } ${selected ? "ring-2 ring-teal ring-offset-2" : ""}`}
    >
      <Handle type="target" position={vertical ? Position.Top : Position.Left} className={handleCls} isConnectable={editable} />
      <div className="flex min-w-0 items-center gap-1.5 text-body-m font-semibold">
        {Icon && <Icon aria-hidden size={14} strokeWidth={2.5} className="shrink-0" />}
        {node.code && <span className="shrink-0">{node.code}</span>}
        <span className="truncate">{node.title}</span>
        {root && (
          <span className={`ml-auto inline-flex shrink-0 items-center gap-1 rounded-full px-1.5 py-0.5 text-caps font-semibold ${ROOT_CAUSE.className}`}>
            <RootIcon aria-hidden size={10} />
            GỐC
          </span>
        )}
      </div>
      <p className="truncate text-body-s opacity-80">
        {look && <span className="font-semibold">{look.label}</span>}
        {look && detail && " · "}
        {detail}
      </p>
      <Handle type="source" position={vertical ? Position.Bottom : Position.Right} className={handleCls} isConnectable={editable} />
    </div>
  );
}

const nodeTypes = { skill: SkillNodeView };

export function SkillTree({
  mode,
  nodes,
  edges,
  mastery,
  heat,
  details,
  rootCauseKey,
  selectedKey,
  direction = "TB",
  height = 480,
  legend = true,
  onNodeClick,
  onNodeMove,
  onConnect,
}: SkillTreeProps) {
  const editable = mode === "edit";
  const vertical = direction === "TB";

  const flowNodes = useMemo<SkillFlowNode[]>(() => {
    const pos = layoutTree(nodes, edges, direction);
    const lookOf = (key: string): Look | null => {
      if (mode === "heatmap") return HEAT[heat?.[key] ?? "GREY"];
      const state = mastery?.[key] ?? (mode === "learner" ? "LOCKED" : undefined);
      return state ? MASTERY[state] : null;
    };
    return nodes.map((n) => ({
      id: n.key,
      type: "skill",
      position: pos.get(n.key)!,
      // Khai sẵn kích thước + vị trí handle để cạnh vẽ được ngay, không chờ đo DOM (kiểu SSR của React Flow).
      width: NODE_W,
      height: NODE_H,
      handles: vertical
        ? [
            { type: "target", position: Position.Top, x: NODE_W / 2, y: 0 },
            { type: "source", position: Position.Bottom, x: NODE_W / 2, y: NODE_H },
          ]
        : [
            { type: "target", position: Position.Left, x: 0, y: NODE_H / 2 },
            { type: "source", position: Position.Right, x: NODE_W, y: NODE_H / 2 },
          ],
      draggable: editable,
      connectable: editable,
      data: {
        node: n,
        look: lookOf(n.key),
        detail: details?.[n.key] ?? [n.chapterRef, `Bloom: ${BLOOM_LABEL[n.bloomLevel]}`].filter(Boolean).join(" · "),
        root: n.key === rootCauseKey,
        selected: n.key === selectedKey,
        editable,
        vertical,
      },
    }));
  }, [nodes, edges, direction, mode, mastery, heat, details, rootCauseKey, selectedKey, editable, vertical]);

  const flowEdges = useMemo<Edge[]>(
    () =>
      edges.map((e) => ({
        id: `${e.fromKey}->${e.toKey}`,
        source: e.fromKey,
        target: e.toKey,
        type: "smoothstep",
        markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: "var(--color-ink-300)" },
        // Cạnh AI đề xuất (chưa GV xác nhận) vẽ nét đứt ở trình sửa cây
        style: { stroke: "var(--color-ink-300)", strokeWidth: 1.5, strokeDasharray: editable && e.source === "AI" ? "5 4" : undefined },
        ariaLabel: `${e.fromKey} là tiên quyết của ${e.toKey}`,
      })),
    [edges, editable],
  );

  // Kéo thả ở chế độ sửa: giữ vị trí cục bộ; dữ liệu mới từ props thì đặt lại.
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState<SkillFlowNode>(flowNodes);
  useEffect(() => setRfNodes(flowNodes), [flowNodes, setRfNodes]);

  return (
    <div className="flex flex-col gap-3">
      <div style={{ height }} className="overflow-hidden rounded-lg border border-line-soft bg-app">
        <ReactFlow<SkillFlowNode>
          nodes={rfNodes}
          edges={flowEdges}
          nodeTypes={nodeTypes}
          onNodesChange={editable ? onNodesChange : undefined}
          onNodeClick={(_, n) => onNodeClick?.(n.data.node)}
          onNodeDragStop={(_, n) => onNodeMove?.(n.id, n.position)}
          onConnect={(c) => c.source && c.target && onConnect?.(c.source, c.target)}
          nodesDraggable={editable}
          nodesConnectable={editable}
          elementsSelectable={editable}
          edgesFocusable={false}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          minZoom={0.3}
          proOptions={{ hideAttribution: true }}
          aria-label="Cây kỹ năng"
        >
          <Background gap={24} color="var(--color-line-soft)" />
          <Controls showInteractive={false} position="top-right" />
        </ReactFlow>
      </div>
      {legend && <StatusLegend kind={mode === "heatmap" ? "heat" : "mastery"} />}
    </div>
  );
}
