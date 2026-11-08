import type { Schema } from "./api";
import type { HeatColor } from "./status";

/**
 * Thống kê lớp cho giảng viên (GV-05, tab "Thống kê"). Mọi hàm là hàm thuần tính từ ảnh chụp heatmap,
 * nên realtime (heatmap.cell / heatmap.node) tự làm biểu đồ đổi theo mà không gọi thêm API.
 */
export type Snapshot = Schema<"HeatmapSnapshot">;
export type Row = Schema<"GridRow">;
export type Stat = Schema<"NodeStat">;
type State = Schema<"MasteryState">;

/** Bộ lọc, đồng bộ với URL (xem `filtersFromParams`). Bỏ trống = không lọc. */
export interface Filters {
  group?: HeatColor; // nhóm màu của SV
  q?: string; // tên / MSSV
  chapter?: string;
  bloom?: string;
  nodeColor?: HeatColor; // màu của nút
  rootOnly?: boolean; // chỉ nút gốc ◎
  nodeKey?: string; // SV theo trạng thái tại nút này …
  nodeState?: "PASSED" | "NOT_PASSED" | "IN_PROGRESS"; // … ở trạng thái này
}

const PARAM: Record<keyof Filters, string> = {
  group: "nhom",
  q: "q",
  chapter: "chuong",
  bloom: "bloom",
  nodeColor: "mau",
  rootOnly: "goc",
  nodeKey: "nut",
  nodeState: "tt",
};
const COLORS = ["GREEN", "YELLOW", "RED", "GREY"];
const NODE_STATES = ["PASSED", "NOT_PASSED", "IN_PROGRESS"];

export function filtersFromParams(p: URLSearchParams): Filters {
  const f: Filters = {};
  const g = p.get(PARAM.group);
  if (g && COLORS.includes(g)) f.group = g as HeatColor;
  const nc = p.get(PARAM.nodeColor);
  if (nc && COLORS.includes(nc)) f.nodeColor = nc as HeatColor;
  const ns = p.get(PARAM.nodeState);
  if (ns && NODE_STATES.includes(ns)) f.nodeState = ns as Filters["nodeState"];
  for (const k of ["q", "chapter", "bloom", "nodeKey"] as const) {
    const v = p.get(PARAM[k]);
    if (v) f[k] = v;
  }
  if (p.get(PARAM.rootOnly) === "1") f.rootOnly = true;
  return f;
}

/** Ghi bộ lọc vào bản sao của `base` (giữ nguyên tham số khác trên URL). */
export function filtersToParams(
  f: Filters,
  base = new URLSearchParams(),
): URLSearchParams {
  const p = new URLSearchParams(base);
  for (const k of Object.keys(PARAM) as (keyof Filters)[]) p.delete(PARAM[k]);
  for (const k of Object.keys(PARAM) as (keyof Filters)[]) {
    const v = f[k];
    if (v) p.set(PARAM[k], v === true ? "1" : String(v));
  }
  return p;
}

export const activeFilterCount = (f: Filters) =>
  Object.values(f).filter(Boolean).length;

const ATTEMPTED: State[] = [
  "IN_PROGRESS",
  "MASTERED",
  "NOT_PASSED",
  "NEEDS_REVERIFY",
];
const PASSED: State[] = ["MASTERED", "NEEDS_REVERIFY"];

/** Nhóm màu của một SV theo tỉ lệ nút Đạt trên `nodes` (≥70% xanh, 40–70% vàng, <40% đỏ, chưa có dữ liệu xám). */
export function studentHeat(
  r: Row,
  nodes: Stat[],
): { color: HeatColor; pct: number | null; passed: number } {
  const states = nodes.map((n) =>
    n.nodeKey ? r.statesByKey?.[n.nodeKey] : undefined,
  );
  const passed = states.filter((x) => x === "MASTERED").length;
  if (
    nodes.length === 0 ||
    states.every((x) => !x || x === "LOCKED" || x === "AVAILABLE")
  )
    return { color: "GREY", pct: null, passed };
  const rate = passed / nodes.length;
  return {
    color: rate >= 0.7 ? "GREEN" : rate >= 0.4 ? "YELLOW" : "RED",
    pct: Math.round(rate * 100),
    passed,
  };
}

export interface NodeMeta {
  chapter: string;
  bloom: string;
}
/** key nút → chương, mức Bloom (từ cây đang phát hành). Không có cây thì map rỗng. */
export function nodeMeta(s: Snapshot): Map<string, NodeMeta> {
  const m = new Map<string, NodeMeta>();
  for (const n of s.tree?.nodes ?? [])
    m.set(n.key, {
      chapter: n.chapterRef ?? "Chưa gán chương",
      bloom: n.bloomLevel,
    });
  return m;
}

/** Nút còn lại sau khi lọc theo chương / Bloom / màu nút / nút gốc. */
export function filterNodes(s: Snapshot, f: Filters): Stat[] {
  const meta = nodeMeta(s);
  return s.nodes.filter((n) => {
    const m = n.nodeKey ? meta.get(n.nodeKey) : undefined;
    if (f.chapter && m?.chapter !== f.chapter) return false;
    if (f.bloom && m?.bloom !== f.bloom) return false;
    if (f.nodeColor && n.color !== f.nodeColor) return false;
    if (f.rootOnly && !n.isRootCause) return false;
    return true;
  });
}

/** SV còn lại sau khi lọc theo tên/MSSV, trạng thái tại một nút và nhóm màu (tính trên `nodes` đã lọc). */
export function filterStudents(s: Snapshot, f: Filters, nodes: Stat[]): Row[] {
  const q = f.q?.trim().toLowerCase();
  return s.grid.filter((r) => {
    if (q && !`${r.studentName} ${r.studentCode}`.toLowerCase().includes(q))
      return false;
    if (f.nodeKey && f.nodeState) {
      const st = r.statesByKey?.[f.nodeKey];
      const ok =
        f.nodeState === "PASSED"
          ? st && PASSED.includes(st)
          : st === f.nodeState;
      if (!ok) return false;
    }
    if (f.group && studentHeat(r, nodes).color !== f.group) return false;
    return true;
  });
}

export const BANDS: HeatColor[] = ["GREEN", "YELLOW", "RED", "GREY"];

export function distribution(
  rows: Row[],
  nodes: Stat[],
): Record<HeatColor, number> {
  const d: Record<HeatColor, number> = { GREEN: 0, YELLOW: 0, RED: 0, GREY: 0 };
  for (const r of rows) d[studentHeat(r, nodes).color]++;
  return d;
}

export interface NodeRate {
  node: Stat;
  attempted: number;
  passed: number;
  rate: number | null; // null = chưa đủ mẫu / chưa ai thử
  attemptedRate: number; // đã thử / số SV đang xét, 0–1
  color: HeatColor;
  sample: "NO_ATTEMPT" | "INSUFFICIENT" | "SUFFICIENT";
}

/**
 * Tỉ lệ Đạt từng nút. Không lọc SV → dùng số liệu máy chủ (đúng luật mẫu tối thiểu của lớp);
 * có lọc SV → tính lại từ các hàng còn lại, mẫu tối thiểu mặc định 3 (hoặc nhỏ hơn nếu lớp có nút đủ mẫu với ít SV hơn).
 */
export function nodeRates(
  s: Snapshot,
  nodes: Stat[],
  rows: Row[],
  studentsFiltered: boolean,
): NodeRate[] {
  const minSample = Math.min(
    3,
    ...s.nodes
      .filter((n) => n.sample === "SUFFICIENT")
      .map((n) => n.attemptedCount),
  );
  return nodes.map((node) => {
    if (!studentsFiltered) {
      const sample =
        node.sample ??
        (node.attemptedCount === 0 ? "NO_ATTEMPT" : "SUFFICIENT");
      return {
        node,
        attempted: node.attemptedCount,
        passed: node.passedCount,
        rate: sample === "SUFFICIENT" ? node.passRate : null,
        attemptedRate: s.enrolledCount
          ? node.attemptedCount / s.enrolledCount
          : 0,
        color: node.color,
        sample,
      };
    }
    const states = rows.map((r) =>
      node.nodeKey ? r.statesByKey?.[node.nodeKey] : undefined,
    );
    const attempted = states.filter((x) => x && ATTEMPTED.includes(x)).length;
    const passed = states.filter((x) => x && PASSED.includes(x)).length;
    const sample =
      attempted === 0
        ? "NO_ATTEMPT"
        : attempted < minSample
          ? "INSUFFICIENT"
          : "SUFFICIENT";
    const rate = sample === "SUFFICIENT" ? passed / attempted : null;
    const color: HeatColor =
      rate == null
        ? "GREY"
        : rate >= 0.7
          ? "GREEN"
          : rate >= 0.4
            ? "YELLOW"
            : "RED";
    return {
      node,
      attempted,
      passed,
      rate,
      attemptedRate: rows.length ? attempted / rows.length : 0,
      color,
      sample,
    };
  });
}

/** Nút yếu nhất lên đầu; nút chưa đủ mẫu xuống cuối. */
export function weakest(rates: NodeRate[]): NodeRate[] {
  return [...rates].sort(
    (a, b) =>
      (a.rate ?? 2) - (b.rate ?? 2) ||
      a.node.code.localeCompare(b.node.code, "vi", { numeric: true }),
  );
}

/** Tỉ lệ Đạt gộp theo chương hoặc mức Bloom (tổng Đạt / tổng đã thử, không lấy trung bình các tỉ lệ). */
export function groupRates(
  s: Snapshot,
  rates: NodeRate[],
  by: "chapter" | "bloom",
): { label: string; rate: number | null; nodes: number; attempted: number }[] {
  const meta = nodeMeta(s);
  const acc = new Map<
    string,
    { passed: number; attempted: number; nodes: number }
  >();
  for (const r of rates) {
    const m = r.node.nodeKey ? meta.get(r.node.nodeKey) : undefined;
    const label = m
      ? m[by]
      : by === "chapter"
        ? "Chưa gán chương"
        : "Chưa gán mức";
    const g = acc.get(label) ?? { passed: 0, attempted: 0, nodes: 0 };
    if (r.sample === "SUFFICIENT") {
      g.passed += r.passed;
      g.attempted += r.attempted;
    }
    g.nodes++;
    acc.set(label, g);
  }
  return [...acc].map(([label, g]) => ({
    label,
    rate: g.attempted ? g.passed / g.attempted : null,
    nodes: g.nodes,
    attempted: g.attempted,
  }));
}

export interface Summary {
  total: number;
  withData: number;
  avgPct: number | null;
  attention: number; // SV nhóm đỏ
  inProgress: number; // ô đang giảng
  online: number;
}
export function summarize(s: Snapshot, rows: Row[], nodes: Stat[]): Summary {
  const heats = rows.map((r) => studentHeat(r, nodes));
  const withData = heats.filter((h) => h.pct != null);
  return {
    total: rows.length,
    withData: withData.length,
    avgPct: withData.length
      ? Math.round(
          withData.reduce((t, h) => t + (h.pct ?? 0), 0) / withData.length,
        )
      : null,
    attention: heats.filter((h) => h.color === "RED").length,
    inProgress: rows.reduce(
      (t, r) =>
        t +
        nodes.filter(
          (n) => n.nodeKey && r.statesByKey?.[n.nodeKey] === "IN_PROGRESS",
        ).length,
      0,
    ),
    online: s.onlineCount,
  };
}

/** CSV theo bộ lọc hiện tại (một dòng một SV; ẩn tên khi `anonymize`). Bọc dấu ngoặc kép để tên có dấu phẩy không vỡ cột. */
export function toCsv(rows: Row[], nodes: Stat[], anonymize: boolean): string {
  const esc = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`;
  const head = [
    "STT",
    ...(anonymize ? [] : ["MSSV", "Họ tên"]),
    "Nhóm",
    "% nút Đạt",
    ...nodes.map((n) => n.code),
  ];
  const body = rows.map((r, i) => {
    const h = studentHeat(r, nodes);
    return [
      i + 1,
      ...(anonymize ? [] : [r.studentCode, r.studentName]),
      h.color,
      h.pct ?? "",
      ...nodes.map((n) => (n.nodeKey && r.statesByKey?.[n.nodeKey]) || ""),
    ]
      .map(esc)
      .join(",");
  });
  return "﻿" + [head.map(esc).join(","), ...body].join("\r\n");
}
