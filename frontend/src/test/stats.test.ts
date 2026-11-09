import { activeFilterCount, distribution, filterNodes, filterStudents, filtersFromParams, filtersToParams, groupRates, nodeRates, summarize, toCsv, weakest, type Snapshot } from "../lib/stats";

const node = (k: string, over: Record<string, unknown> = {}) => ({ nodeId: `id-${k}`, nodeKey: k, code: k.toUpperCase(), title: k, color: "GREEN", passRate: 0.9, attemptedCount: 10, passedCount: 9, isRootCause: false, sample: "SUFFICIENT", ...over });
const row = (i: number, st: Record<string, string>) => ({ studentId: `s${i}`, studentName: `Nguyễn Văn ${i}`, studentCode: `312${i}`, states: {}, progress: 0, masteredCount: 0, statesByKey: st });
const SNAP = {
  classId: "c1",
  enrolledCount: 4,
  onlineCount: 2,
  activeSessions: 0,
  nodes: [node("n1"), node("n2", { color: "RED", passRate: 0.2, passedCount: 2, isRootCause: true }), node("n3", { color: "GREY", passRate: null, attemptedCount: 1, passedCount: 0, sample: "INSUFFICIENT" })],
  grid: [
    row(1, { n1: "MASTERED", n2: "MASTERED", n3: "MASTERED" }), // 100% xanh
    row(2, { n1: "MASTERED", n2: "NOT_PASSED" }), // 33% đỏ
    row(3, { n1: "NOT_PASSED", n2: "IN_PROGRESS" }), // 0% đỏ
    row(4, {}), // chưa có dữ liệu
  ],
  alerts: [],
  tree: {
    id: "v",
    versionNo: 1,
    status: "PUBLISHED",
    nodes: [
      { id: "id-n1", key: "n1", title: "n1", chapterRef: "Chương 1", bloomLevel: "REMEMBER" },
      { id: "id-n2", key: "n2", title: "n2", chapterRef: "Chương 2", bloomLevel: "APPLY" },
      { id: "id-n3", key: "n3", title: "n3", chapterRef: "Chương 2", bloomLevel: "APPLY" },
    ],
    edges: [],
  },
} as unknown as Snapshot;

describe("bộ lọc ↔ URL", () => {
  it("đi qua URL rồi về giữ nguyên, bỏ qua giá trị rác và giữ tham số khác", () => {
    const f = { group: "RED", chapter: "Chương 2", rootOnly: true, nodeKey: "n2", nodeState: "NOT_PASSED" } as const;
    const p = filtersToParams(f, new URLSearchParams("tab=thong-ke"));
    expect(p.get("tab")).toBe("thong-ke");
    expect(filtersFromParams(p)).toEqual(f);
    expect(filtersFromParams(new URLSearchParams("nhom=TIM&tt=XYZ&goc=0"))).toEqual({});
    expect(activeFilterCount(f)).toBe(5);
  });
});

describe("lọc và tổng hợp", () => {
  it("lọc nút theo chương, Bloom, nút gốc", () => {
    expect(filterNodes(SNAP, { chapter: "Chương 2" }).map((n) => n.code)).toEqual(["N2", "N3"]);
    expect(filterNodes(SNAP, { bloom: "REMEMBER" }).map((n) => n.code)).toEqual(["N1"]);
    expect(filterNodes(SNAP, { rootOnly: true }).map((n) => n.code)).toEqual(["N2"]);
  });
  it("lọc SV theo tên, nhóm màu và trạng thái tại một nút", () => {
    const nodes = SNAP.nodes;
    expect(filterStudents(SNAP, { q: "văn 2" }, nodes)).toHaveLength(1);
    expect(filterStudents(SNAP, { group: "RED" }, nodes).map((r) => r.studentId)).toEqual(["s2", "s3"]);
    expect(filterStudents(SNAP, { nodeKey: "n2", nodeState: "NOT_PASSED" }, nodes).map((r) => r.studentId)).toEqual(["s2"]);
    expect(filterStudents(SNAP, { nodeKey: "n1", nodeState: "PASSED" }, nodes)).toHaveLength(2);
  });
  it("phân bố và tóm tắt", () => {
    expect(distribution(SNAP.grid, SNAP.nodes)).toEqual({ GREEN: 1, YELLOW: 0, RED: 2, GREY: 1 });
    const s = summarize(SNAP, SNAP.grid, SNAP.nodes);
    expect(s).toMatchObject({ total: 4, withData: 3, attention: 2, inProgress: 1, online: 2 });
    expect(s.avgPct).toBe(Math.round((100 + 33 + 0) / 3));
  });
});

describe("tỉ lệ Đạt theo nút", () => {
  it("không lọc SV: dùng số liệu máy chủ, nút ít mẫu có rate = null và xuống cuối bảng yếu nhất", () => {
    const r = nodeRates(SNAP, SNAP.nodes, SNAP.grid, false);
    expect(r.map((x) => x.rate)).toEqual([0.9, 0.2, null]);
    expect(weakest(r).map((x) => x.node.code)).toEqual(["N2", "N1", "N3"]);
  });
  it("có lọc SV: tính lại từ các hàng còn lại", () => {
    const rows = filterStudents(SNAP, { group: "RED" }, SNAP.nodes); // s2, s3
    const r = nodeRates(SNAP, SNAP.nodes, rows, true);
    expect(r[0]).toMatchObject({ attempted: 2, passed: 1 });
    expect(r[0]).toMatchObject({ sample: "INSUFFICIENT", rate: null }); // chỉ 2 SV thử, dưới mẫu tối thiểu 3
    expect(r[2].sample).toBe("NO_ATTEMPT");
    const full = nodeRates(SNAP, SNAP.nodes, SNAP.grid, true); // 3 SV thử N1, 2 Đạt
    expect(full[0].rate).toBeCloseTo(2 / 3);
  });
  it("gộp theo chương lấy tổng Đạt / tổng đã thử, bỏ nút ít mẫu", () => {
    const g = groupRates(SNAP, nodeRates(SNAP, SNAP.nodes, SNAP.grid, false), "chapter");
    expect(g.find((x) => x.label === "Chương 2")).toMatchObject({ nodes: 2, attempted: 10 });
    expect(g.find((x) => x.label === "Chương 2")?.rate).toBeCloseTo(0.2);
  });
});

describe("toCsv", () => {
  it("có BOM, thoát dấu ngoặc kép, và ẩn tên khi chiếu", () => {
    const rows = [row(1, { n1: "MASTERED" })];
    rows[0].studentName = 'Trần "Bo", Châu';
    const csv = toCsv(rows as never, SNAP.nodes, false);
    expect(csv.startsWith("﻿")).toBe(true);
    expect(csv).toContain('"Trần ""Bo"", Châu"');
    expect(toCsv(rows as never, SNAP.nodes, true)).not.toContain("Trần");
  });
});
