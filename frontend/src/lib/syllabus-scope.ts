/** Khoanh vùng giáo trình trước khi dựng cây (GV-03): đổi chương đã tick / khoảng trang gõ tay thành các khoảng trang gửi backend. */
import type { Schema } from "./api";

export type Range = [number, number];
type Report = Schema<"TocReport">;
type Chapter = Schema<"TocChapter">;

/** Gộp các khoảng chồng hoặc liền nhau: [1,4] + [5,9] → [1,9]. */
export function mergeRanges(ranges: Range[]): Range[] {
  const sorted = [...ranges].sort((a, b) => a[0] - b[0]);
  const out: Range[] = [];
  for (const [from, to] of sorted) {
    const last = out[out.length - 1];
    if (last && from <= last[1] + 1) last[1] = Math.max(last[1], to);
    else out.push([from, to]);
  }
  return out;
}

export const pagesIn = (ranges: Range[]): number => ranges.reduce((s, [a, b]) => s + b - a + 1, 0);

/** Chọn chương theo số trang chỉ khi MỌI chương đều biết trang đầu–cuối; nếu không, GV nhập khoảng trang. */
export const hasPageMap = (chapters: Chapter[]): boolean =>
  chapters.length > 0 && chapters.every((c) => c.startPage != null && c.endPage != null);

export function rangesFromChapters(chapters: Chapter[], selected: ReadonlySet<number>): Range[] {
  const out: Range[] = [];
  for (const c of chapters) {
    if (selected.has(c.index) && c.startPage != null && c.endPage != null) out.push([c.startPage, c.endPage]);
  }
  return mergeRanges(out);
}

/** Mặc định: AI đề xuất giữ chương nào thì chỉ tick các chương đó; không thì tick hết trừ chương AI đề xuất bỏ. */
export function defaultSelected(report: Pick<Report, "chapters" | "advice">): Set<number> {
  const { keep, skip } = report.advice;
  if (keep.length) return new Set(keep);
  const skipped = new Set(skip.map((s) => s.index));
  return new Set(report.chapters.map((c) => c.index).filter((i) => !skipped.has(i)));
}

/** "10-45, 60" → [[10,45],[60,60]]. Rỗng ⇒ không lỗi, không khoảng (nghĩa là chưa chọn). */
export function parsePageRanges(text: string, pageCount: number): { ranges: Range[]; error?: string } {
  const parts = text
    .replace(/[–—]/g, "-")
    .split(/[,;]/)
    .map((s) => s.trim())
    .filter(Boolean);
  const ranges: Range[] = [];
  for (const p of parts) {
    const m = /^(\d+)(?:\s*-\s*(\d+))?$/.exec(p);
    if (!m) return { ranges: [], error: `"${p}" không đúng dạng – hãy gõ như 10-45, 60-80.` };
    const from = Number(m[1]);
    const to = m[2] ? Number(m[2]) : from;
    if (from < 1 || to < from || to > pageCount) {
      return { ranges: [], error: `Khoảng "${p}" nằm ngoài trang 1–${pageCount} hoặc bị ngược.` };
    }
    ranges.push([from, to]);
  }
  return { ranges: mergeRanges(ranges) };
}

export type Detail = "SUMMARY" | "STANDARD" | "DETAILED";
/** Menu mức chi tiết cố định (số khái niệm tối đa mỗi đoạn lấy từ `report.detailCaps`). */
export const DETAILS: { key: Detail; label: string; hint: string }[] = [
  { key: "SUMMARY", label: "Tóm lược", hint: "ít nút nhất, chỉ ý lớn" },
  { key: "STANDARD", label: "Chuẩn", hint: "cân bằng" },
  { key: "DETAILED", label: "Chi tiết", hint: "nhiều nút nhất, tốn nhất" },
];

export interface ScopeEstimate {
  chunks: number;
  nodes: number;
  calls: number;
}

/** Số lượt gọi AI trích khái niệm cho phần GV chọn: mỗi chương tối thiểu một đoạn; chọn theo trang thì suy từ số ký tự trung bình. */
export function chunksFor(report: Report, selected: ReadonlySet<number>, ranges: Range[]): number {
  const per = report.charsPerChunk || 7000;
  if (hasPageMap(report.chapters)) {
    return report.chapters.filter((c) => selected.has(c.index)).reduce((s, c) => s + Math.max(1, Math.ceil((c.chars ?? 0) / per)), 0);
  }
  const pages = pagesIn(ranges);
  const chars = report.totalPages ? (pages * report.totalChars) / report.totalPages : 0;
  return pages ? Math.max(1, Math.ceil(chars / per)) : 0;
}

/** Cùng công thức với `estimate_size` của backend (hằng số lấy từ báo cáo): nút = đoạn × nút/đoạn; lượt gọi = đoạn + nút (+ nút nếu sinh rubric ngay). */
export function estimateScope(report: Report, chunks: number, detail: Detail, lazyRubric: boolean): ScopeEstimate {
  const nodes = chunks * (report.nodesPerChunk?.[detail] ?? 11);
  return { chunks, nodes, calls: chunks + nodes + (lazyRubric ? 0 : nodes) };
}
