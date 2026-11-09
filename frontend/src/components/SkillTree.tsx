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
  MiniMap,
  Position,
  ReactFlow,
  useNodesState,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { CircleCheck, Clock, Maximize2, Minimize2, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
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
  /** Cạnh tạo chu trình gây lỗi (vẽ đường đỏ cảnh báo trực quan – BR-01) */
  cycleEdge?: { fromKey: string; toKey: string } | null;
  /** Xóa cảnh báo chu trình khi thao tác khác trên cây */
  onClearCycleEdge?: () => void;
  onPaneClick?: () => void;
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

function EditLegend() {
  return (
    <div className="flex flex-wrap items-center gap-4 text-body-s text-ink-700" aria-label="Chú giải trạng thái biên tập">
      <span className="font-semibold text-ink-900">Chú giải:</span>
      <span className="flex items-center gap-1.5 rounded border border-teal/40 bg-teal-soft px-2 py-0.5 font-medium text-teal">
        <CircleCheck size={14} /> Đã duyệt
      </span>
      <span className="flex items-center gap-1.5 rounded border border-honey/60 bg-honey-soft px-2 py-0.5 font-medium text-honey-deep">
        <Clock size={14} /> Chưa duyệt
      </span>
      <span className="flex items-center gap-1.5 rounded border border-dashed border-ink-300 bg-surface px-2 py-0.5 font-medium text-ink-500">
        <TriangleAlert size={14} /> Chưa có rubric
      </span>
      <span className="flex items-center gap-1.5 text-ink-500">
        <span className="inline-block w-4 border-b-2 border-dashed border-ink-400"></span> Nét đứt = Cạnh AI đề xuất
      </span>
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
  cycleEdge,
  onClearCycleEdge,
  onPaneClick,
  onNodeClick,
  onNodeMove,
  onConnect,
}: SkillTreeProps) {
  const editable = mode === "edit";
  const vertical = direction === "TB";
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFullscreen(false);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const pos = useMemo(() => layoutTree(nodes, edges, direction), [nodes, edges, direction]);

  const flowNodes = useMemo<SkillFlowNode[]>(() => {
    const lookOf = (key: string): Look | null => {
      if (mode === "heatmap") return HEAT[heat?.[key] ?? "GREY"];
      if (mode === "edit") {
        const n = nodes.find((x) => x.key === key);
        if (!n?.rubric) {
          return {
            label: "Chưa có rubric",
            icon: TriangleAlert,
            className: "border-dashed border-ink-300 bg-surface text-ink-500",
          };
        }
        if (!n.rubric.approved) {
          return {
            label: "Chưa duyệt",
            icon: Clock,
            className: "border-honey/60 bg-honey-soft text-honey-deep",
          };
        }
        return {
          label: "Đã duyệt",
          icon: CircleCheck,
          className: "border-teal/40 bg-teal-soft text-teal",
        };
      }
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
  }, [nodes, pos, direction, mode, mastery, heat, details, rootCauseKey, selectedKey, editable, vertical]);

  const flowEdges = useMemo<Edge[]>(() => {
    const list: Edge[] = edges.map((e) => ({
      id: `${e.fromKey}->${e.toKey}`,
      source: e.fromKey,
      target: e.toKey,
      type: "smoothstep",
      markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: "var(--color-ink-300)" },
      // Cạnh AI đề xuất (chưa GV xác nhận) vẽ nét đứt ở trình sửa cây
      style: { stroke: "var(--color-ink-300)", strokeWidth: 1.5, strokeDasharray: editable && e.source === "AI" ? "5 4" : undefined },
      ariaLabel: `${e.fromKey} là tiên quyết của ${e.toKey}`,
    }));
    // Nếu có cạnh gây chu trình: vẽ đường đỏ cảnh báo nổi bật (BR-01)
    if (cycleEdge) {
      list.push({
        id: `cycle-${cycleEdge.fromKey}->${cycleEdge.toKey}`,
        source: cycleEdge.fromKey,
        target: cycleEdge.toKey,
        type: "smoothstep",
        animated: true,
        markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18, color: "#ef4444" },
        style: { stroke: "#ef4444", strokeWidth: 3 },
        ariaLabel: `Cạnh tạo chu trình: ${cycleEdge.fromKey} đến ${cycleEdge.toKey}`,
      });
    }
    return list;
  }, [edges, editable, cycleEdge]);

  // Kéo thả ở chế độ sửa: giữ vị trí cục bộ; dữ liệu mới từ props thì đặt lại.
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState<SkillFlowNode>(flowNodes);
  useEffect(() => setRfNodes(flowNodes), [flowNodes, setRfNodes]);

  return (
    <div className={`flex flex-col gap-3 ${fullscreen ? "fixed inset-0 z-50 bg-app p-4 shadow-2xl" : ""}`}>
      <div className="relative">
        <button
          type="button"
          onClick={() => setFullscreen((f) => !f)}
          aria-label={fullscreen ? "Thu nhỏ màn hình" : "Toàn màn hình"}
          title={fullscreen ? "Thu nhỏ màn hình (Esc)" : "Toàn màn hình"}
          className="absolute left-3 top-3 z-10 flex items-center gap-1.5 rounded-md border border-line-strong bg-surface/90 px-2.5 py-1 text-body-s font-medium text-ink-700 shadow-sm backdrop-blur hover:bg-surface"
        >
          {fullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          <span>{fullscreen ? "Thu nhỏ" : "Toàn màn hình"}</span>
        </button>
        <div style={{ height: fullscreen ? "calc(100vh - 80px)" : height }} className="overflow-hidden rounded-lg border border-line-soft bg-app">
          <ReactFlow<SkillFlowNode>
            nodes={rfNodes}
            edges={flowEdges}
            nodeTypes={nodeTypes}
            onNodesChange={editable ? onNodesChange : undefined}
            onNodeClick={(_, n) => {
              onClearCycleEdge?.();
              onNodeClick?.(n.data.node);
            }}
            onPaneClick={() => {
              onClearCycleEdge?.();
              onPaneClick?.();
            }}
            onNodeDragStart={() => onClearCycleEdge?.()}
            onNodeDragStop={(_, n) => onNodeMove?.(n.id, n.position)}
            onConnect={(c) => {
              onClearCycleEdge?.();
              if (c.source && c.target) onConnect?.(c.source, c.target);
            }}
            nodesDraggable={editable}
            nodesConnectable={editable}
            elementsSelectable={editable}
            deleteKeyCode={null} // React Flow mặc định xóa nút đang chọn khi bấm Backspace: nút biến mất mà không gọi API
            edgesFocusable={false}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            minZoom={0.1}
            onlyRenderVisibleElements={nodes.length > 30}
            proOptions={{ hideAttribution: true }}
            aria-label="Cây kỹ năng"
          >
            <Background gap={24} color="var(--color-line-soft)" />
            <Controls showInteractive={false} position="top-right" />
            <MiniMap
              position="bottom-right"
              zoomable
              pannable
              aria-label="Bản đồ thu nhỏ"
              className="!border !border-line-soft !bg-surface"
              nodeColor={(n) => {
                const look = (n.data as SkillNodeData)?.look;
                if (look?.label === "Đã duyệt") return "#0d9488";
                if (look?.label === "Chưa duyệt") return "#d97706";
                if (look?.label === "Chưa có rubric") return "#94a3b8";
                return "#cbd5e1";
              }}
            />
          </ReactFlow>
        </div>
      </div>
      {legend && (mode === "edit" ? <EditLegend /> : <StatusLegend kind={mode === "heatmap" ? "heat" : "mastery"} />)}
    </div>
  );
}
