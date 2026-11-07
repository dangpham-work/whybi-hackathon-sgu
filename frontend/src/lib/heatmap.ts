import type { Schema } from "./api";
import type { HeatColor } from "./status";

export type Snapshot = Schema<"HeatmapSnapshot">;
export type Alert = Schema<"HeatmapAlert">;
export type WsEventLike = { event: string; payload: unknown };
type MasteryState = Schema<"MasteryState">;

/** Payload `heatmap.cell` (backend/app/models/schemas/mastery.py – không có trong OpenAPI vì chỉ đi qua WebSocket). */
interface CellPayload {
  studentId: string;
  studentName: string;
  studentCode?: string | null;
  nodeId: string;
  nodeKey?: string | null;
  state: MasteryState;
}
/** Payload `heatmap.node`. */
interface NodePayload {
  nodeId: string;
  nodeKey?: string | null;
  color: HeatColor;
  passRate: number | null;
  attemptedRate: number;
  sample?: Schema<"NodeStat">["sample"];
  label?: string | null;
  attemptedCount?: number | null;
  passedCount?: number | null;
}

/**
 * Áp một sự kiện realtime của kênh class:{id}:heatmap lên ảnh chụp (Bảng 5.11, C2-13):
 * heatmap.cell → đổi một ô lưới · heatmap.node → đổi màu / số liệu một nút · heatmap.alert → thêm/ thay cảnh báo.
 * Cảnh báo của nút không còn ĐỎ thì bỏ (như ghi chú ở services/heatmap.py). Không biết sự kiện → giữ nguyên.
 */
export function applyHeatmapEvent(s: Snapshot, e: WsEventLike, anonymize = false): Snapshot {
  if (e.event === "heatmap.cell") {
    const c = e.payload as CellPayload;
    const key = c.nodeKey ?? c.nodeId;
    let found = false;
    const grid = s.grid.map((row) => {
      if (row.studentId !== c.studentId) return row;
      found = true;
      return { ...row, statesByKey: { ...row.statesByKey, [key]: c.state } };
    });
    // chế độ trình chiếu: tên / MSSV trong tin realtime không được lọt ra màn hình (FR-HM-09)
    if (!found)
      grid.push({ studentId: c.studentId, studentName: anonymize ? "" : c.studentName, studentCode: anonymize ? "" : (c.studentCode ?? ""), states: {}, progress: 0, statesByKey: { [key]: c.state }, masteredCount: 0 });
    return { ...s, grid };
  }
  if (e.event === "heatmap.node") {
    const n = e.payload as NodePayload;
    const nodes = s.nodes.map((x) =>
      x.nodeId === n.nodeId
        ? {
            ...x,
            color: n.color,
            passRate: n.passRate,
            attemptedRate: n.attemptedRate,
            sample: n.sample ?? x.sample,
            label: n.label ?? x.label,
            attemptedCount: n.attemptedCount ?? x.attemptedCount,
            passedCount: n.passedCount ?? x.passedCount,
            isRootCause: n.color === "RED" ? x.isRootCause : false,
          }
        : x,
    );
    const alerts = n.color === "RED" ? s.alerts : (s.alerts ?? []).filter((a) => a.nodeId !== n.nodeId);
    return { ...s, nodes, alerts };
  }
  if (e.event === "heatmap.alert") {
    const a = e.payload as Alert;
    const alerts = [...(s.alerts ?? []).filter((x) => x.nodeId !== a.nodeId), a];
    return { ...s, alerts, nodes: s.nodes.map((n) => (n.nodeId === a.rootCauseNodeId ? { ...n, isRootCause: true } : n)) };
  }
  return s;
}

/** Màu theo key nút cho SkillTree mode="heatmap". */
export function heatByKey(s: Snapshot): Record<string, HeatColor> {
  const out: Record<string, HeatColor> = {};
  for (const n of s.nodes) if (n.nodeKey) out[n.nodeKey] = n.color as HeatColor;
  return out;
}

const pct = (r: number | null | undefined) => (r == null ? null : `${Math.round(r * 100)}%`);

/** Dòng phụ dưới tên nút: "32% Đạt · 25 đã thử" hoặc "chưa đủ mẫu". */
export function detailsByKey(s: Snapshot): Record<string, string> {
  const out: Record<string, string> = {};
  for (const n of s.nodes) {
    if (!n.nodeKey) continue;
    out[n.nodeKey] = n.sample === "SUFFICIENT" || n.passRate != null ? `${pct(n.passRate) ?? "–"} Đạt · ${n.attemptedCount} đã thử` : `${n.attemptedCount} SV thử · chưa đủ mẫu`;
  }
  return out;
}

/** Nút gốc của cảnh báo đầu tiên – SkillTree gắn ◎ GỐC. */
export const rootCauseKey = (s: Snapshot): string | null => s.alerts?.find((a) => a.rootCauseNodeKey)?.rootCauseNodeKey ?? null;
