import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { setToken } from "../lib/api";
import { auth } from "../lib/auth";
import { applyHeatmapEvent, type Snapshot } from "../lib/heatmap";
import { routes } from "../router";
import { err, mockApi, ok } from "./mock-api";

let push: (e: { channel: string; event: string; payload: unknown }) => void = () => {};
let channel: string | null = null;
vi.mock("../lib/ws", async (orig) => ({
  ...(await orig<typeof import("../lib/ws")>()),
  useChannel: (ch: string | null, h: typeof push) => {
    channel = ch;
    push = h;
    return "open";
  },
}));
vi.mock("../components/SkillTree", async (orig) => ({
  ...(await orig<typeof import("../components/SkillTree")>()),
  SkillTree: (p: { nodes: { id?: string; key: string; title: string }[]; heat?: Record<string, string>; rootCauseKey?: string | null; onNodeClick?: (n: { id?: string }) => void }) => (
    <ul aria-label="cây">
      {p.nodes.map((n) => (
        <li key={n.key}>
          <button onClick={() => p.onNodeClick?.(n)}>{`${n.title}: ${p.heat?.[n.key] ?? "?"}${p.rootCauseKey === n.key ? " GỐC" : ""}`}</button>
        </li>
      ))}
    </ul>
  ),
}));

const SNAP: Snapshot = {
  classId: "c1",
  enrolledCount: 42,
  onlineCount: 38,
  activeSessions: 11,
  nodes: [
    { nodeId: "i5", nodeKey: "n5", code: "N5", title: "Con trỏ", color: "YELLOW", passRate: 0.5, attemptedCount: 10, passedCount: 5, isRootCause: false },
    { nodeId: "i6", nodeKey: "n6", code: "N6", title: "Cấp phát", color: "GREEN", passRate: 0.9, attemptedCount: 10, passedCount: 9, isRootCause: false },
  ],
  grid: [{ studentId: "s1", studentName: "Trần Bảo Châu", studentCode: "3121001", states: {}, statesByKey: { n5: "IN_PROGRESS" }, progress: 0, masteredCount: 0 }],
  alerts: [],
  tree: {
    id: "v1",
    versionNo: 1,
    status: "PUBLISHED",
    nodes: [
      { id: "i5", key: "n5", title: "Con trỏ", bloomLevel: "UNDERSTAND" },
      { id: "i6", key: "n6", title: "Cấp phát", bloomLevel: "APPLY" },
    ],
    edges: [],
  },
} as unknown as Snapshot;

describe("applyHeatmapEvent", () => {
  it("heatmap.cell đổi đúng ô của SV, thêm SV mới nếu chưa có", () => {
    const a = applyHeatmapEvent(SNAP, { event: "heatmap.cell", payload: { studentId: "s1", studentName: "x", nodeId: "i5", nodeKey: "n5", state: "MASTERED" } });
    expect(a.grid[0].statesByKey?.n5).toBe("MASTERED");
    const b = applyHeatmapEvent(SNAP, { event: "heatmap.cell", payload: { studentId: "s2", studentName: "Lê Dũng", nodeId: "i6", nodeKey: "n6", state: "IN_PROGRESS" } });
    expect(b.grid).toHaveLength(2);
  });
  it("heatmap.node đổi màu; hết ĐỎ thì bỏ cảnh báo của nút", () => {
    const withAlert = { ...SNAP, alerts: [{ nodeId: "i5", rootCauseNodeId: "i5", message: "Nên giảng lại N5" }] } as Snapshot;
    const red = applyHeatmapEvent(withAlert, { event: "heatmap.node", payload: { nodeId: "i5", color: "RED", passRate: 0.2, attemptedRate: 0.5 } });
    expect(red.nodes[0].color).toBe("RED");
    expect(red.alerts).toHaveLength(1);
    const green = applyHeatmapEvent(withAlert, { event: "heatmap.node", payload: { nodeId: "i5", color: "GREEN", passRate: 0.9, attemptedRate: 0.5 } });
    expect(green.alerts).toHaveLength(0);
  });
  it("sự kiện lạ giữ nguyên", () => {
    expect(applyHeatmapEvent(SNAP, { event: "khac", payload: {} })).toBe(SNAP);
  });
});

const me = { "GET /me": ok({ id: "u", fullName: "GV", email: "g@x.vn", role: "LECTURER" }) };
const open = (url: string) => render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [url] })} />);
beforeEach(() => {
  auth.reset();
  setToken("acc-1");
});
afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

describe("GV-05 Dashboard bản đồ nhiệt (GD-10)", () => {
  it("hiện số liệu lớp và nghe đúng kênh của lớp", async () => {
    mockApi({ ...me, "GET /classes/c1/heatmap": ok(SNAP) });
    open("/gv/classes/c1/heatmap");
    expect(await screen.findByText("Con trỏ: YELLOW")).toBeTruthy();
    expect(screen.getByText("38")).toBeTruthy();
    expect(channel).toBe("class:c1:heatmap");
    expect(screen.getByText(/Chưa có điểm nghẽn nào/)).toBeTruthy();
  });

  it("đẩy sự kiện thì màn đổi màu, có cảnh báo mà không tải lại", async () => {
    const m = mockApi({ ...me, "GET /classes/c1/heatmap": ok(SNAP) });
    open("/gv/classes/c1/heatmap");
    await screen.findByText("Con trỏ: YELLOW");
    act(() => push({ channel: "x", event: "heatmap.node", payload: { nodeId: "i5", nodeKey: "n5", color: "RED", passRate: 0.2, attemptedRate: 0.5 } }));
    act(() =>
      push({ channel: "x", event: "heatmap.alert", payload: { nodeId: "i5", nodeKey: "n5", rootCauseNodeId: "i5", rootCauseNodeKey: "n5", message: "Nên giảng lại N5 Con trỏ" } }),
    );
    expect(screen.getByText("Con trỏ: RED GỐC")).toBeTruthy();
    expect(screen.getByText("Nên giảng lại N5 Con trỏ")).toBeTruthy();
    expect(m.called("GET /classes/c1/heatmap")).toHaveLength(1);
  });

  it("chế độ lưới: có tên và MSSV, ô đổi theo heatmap.cell", async () => {
    mockApi({ ...me, "GET /classes/c1/heatmap": ok(SNAP) });
    open("/gv/classes/c1/heatmap");
    fireEvent.click(await screen.findByRole("tab", { name: "Lưới SV × Nút" }));
    const grid = screen.getByRole("table");
    expect(within(grid).getByText("Trần Bảo Châu")).toBeTruthy();
    expect(within(grid).getByText("3121001")).toBeTruthy();
    expect(within(grid).getByLabelText("Đang giảng")).toBeTruthy();
    act(() => push({ channel: "x", event: "heatmap.cell", payload: { studentId: "s1", studentName: "x", nodeId: "i5", nodeKey: "n5", state: "MASTERED" } }));
    expect(within(grid).getByLabelText("Đạt")).toBeTruthy();
  });

  it("bấm nút trên cây mở GV-06 của nút đó", async () => {
    mockApi({ ...me, "GET /classes/c1/heatmap": ok(SNAP), "GET /classes/c1/nodes/i5/detail": err(501, "NOT_IMPLEMENTED") });
    const router = createMemoryRouter(routes, { initialEntries: ["/gv/classes/c1/heatmap"] });
    render(<RouterProvider router={router} />);
    fireEvent.click(await screen.findByText("Con trỏ: YELLOW"));
    expect(router.state.location.pathname).toBe("/gv/classes/c1/nodes/i5");
  });
});

describe("GV-06 Chi tiết nút (GD-10)", () => {
  it("hiện SV theo trạng thái, quan niệm sai và truy vết nút gốc", async () => {
    mockApi({
      ...me,
      "GET /classes/c1/nodes/i5/detail": ok({
        nodeId: "i5",
        stat: { ...SNAP.nodes[0], color: "RED", label: "✗ Điểm nghẽn – 2/9 Đạt", attemptedRate: 0.6, enrolledCount: 25, isRootCause: true },
        studentsByState: { NOT_PASSED: [{ studentId: "s1", studentName: "Trần Bảo Châu", studentCode: "1", states: {}, progress: 0 }], MASTERED: [] },
        topMisconceptions: [{ content: "Con trỏ chứa giá trị của biến", count: 9 }],
        alert: { nodeId: "i5", rootCauseNodeId: "i5", message: "Nên giảng lại N5 Con trỏ", conditionalFailRate: 0.82 },
      }),
    });
    open("/gv/classes/c1/nodes/i5");
    expect(await screen.findByRole("heading", { name: /N5 – Con trỏ/ })).toBeTruthy();
    expect(screen.getByText("Chưa đạt (1)")).toBeTruthy();
    expect(screen.getByText("Trần Bảo Châu")).toBeTruthy();
    expect(screen.getByText("Con trỏ chứa giá trị của biến")).toBeTruthy();
    expect(screen.getByText("9 SV")).toBeTruthy();
    expect(screen.getByText(/0,82/)).toBeTruthy();
    expect(screen.getByText("Điểm nghẽn gốc")).toBeTruthy();
  });
});
