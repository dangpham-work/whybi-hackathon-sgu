import { fireEvent, render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { setToken } from "../lib/api";
import { auth } from "../lib/auth";
import type { Snapshot } from "../lib/stats";
import { routes } from "../router";
import { mockApi, ok } from "./mock-api";

vi.mock("../lib/ws", async (orig) => ({ ...(await orig<typeof import("../lib/ws")>()), useChannel: () => "open" }));
vi.mock("../components/SkillTree", async (orig) => ({ ...(await orig<typeof import("../components/SkillTree")>()), SkillTree: () => <div aria-label="cây" /> }));

const node = (k: string, over: Record<string, unknown> = {}) => ({ nodeId: `id-${k}`, nodeKey: k, code: k.toUpperCase(), title: `Nút ${k}`, color: "GREEN", passRate: 0.9, attemptedCount: 10, passedCount: 9, isRootCause: false, sample: "SUFFICIENT", ...over });
const row = (i: number, st: Record<string, string>) => ({ studentId: `s${i}`, studentName: `Sinh viên ${i}`, studentCode: `3120${i}`, states: {}, progress: 0, masteredCount: 0, statesByKey: st });
const SNAP = {
  classId: "c1",
  enrolledCount: 4,
  onlineCount: 1,
  activeSessions: 0,
  nodes: [node("n1"), node("n2", { color: "RED", passRate: 0.2, passedCount: 2 })],
  grid: [row(1, { n1: "MASTERED", n2: "MASTERED" }), row(2, { n1: "MASTERED", n2: "NOT_PASSED" }), row(3, { n1: "NOT_PASSED", n2: "NOT_PASSED" }), row(4, {})],
  alerts: [],
  tree: { id: "v", versionNo: 1, status: "PUBLISHED", nodes: [{ id: "id-n1", key: "n1", title: "a", chapterRef: "Chương 1", bloomLevel: "REMEMBER" }, { id: "id-n2", key: "n2", title: "b", chapterRef: "Chương 2", bloomLevel: "APPLY" }], edges: [] },
} as unknown as Snapshot;

const me = { "GET /me": ok({ id: "u", fullName: "GV", email: "g@x.vn", role: "LECTURER" }) };
const open = (url = "/gv/classes/c1/heatmap") => {
  const router = createMemoryRouter(routes, { initialEntries: [url] });
  render(<RouterProvider router={router} />);
  return router;
};
beforeEach(() => {
  auth.reset();
  setToken("acc-1");
  mockApi({ ...me, "GET /classes/c1/heatmap": ok(SNAP) });
});
afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

describe("GV-05 tab Thống kê", () => {
  it("có tab Thống kê và link ?tab=thong-ke mở thẳng tab đó", async () => {
    open("/gv/classes/c1/heatmap?tab=thong-ke");
    expect(await screen.findByLabelText("Số liệu tổng quan")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Thống kê" }).getAttribute("aria-selected")).toBe("true");
  });

  it("bấm đoạn đỏ của thanh phân bố thì lọc nhóm đỏ, ghi lên URL và hiện chip", async () => {
    const router = open();
    fireEvent.click(await screen.findByRole("tab", { name: "Thống kê" }));
    const dist = screen.getByRole("group", { name: "Phân bố sinh viên theo nhóm màu" });
    fireEvent.click(within(dist).getByRole("button", { name: /< 40%/ }));
    expect(router.state.location.search).toContain("nhom=RED");
    const chips = screen.getByRole("list", { name: "Bộ lọc đang bật" });
    expect(within(chips).getByText(/Nhóm SV/)).toBeTruthy();
    expect(within(screen.getByRole("list", { name: "Khung màu sinh viên" })).getAllByRole("listitem")).toHaveLength(1);
    fireEvent.click(within(chips).getByRole("button", { name: "Xóa lọc" }));
    expect(router.state.location.search).not.toContain("nhom");
    expect(within(screen.getByRole("list", { name: "Khung màu sinh viên" })).getAllByRole("listitem")).toHaveLength(4);
  });

  it("lọc theo chương thu hẹp danh sách nút; bấm nút yếu nhất mở GV-06", async () => {
    const router = open("/gv/classes/c1/heatmap?tab=thong-ke&chuong=Ch%C6%B0%C6%A1ng%202");
    const list = await screen.findByRole("list", { name: "Nút yếu nhất" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    fireEvent.click(within(list).getByRole("link", { name: /N2/ }));
    expect(router.state.location.pathname).toBe("/gv/classes/c1/nodes/id-n2");
  });

  it("ẩn tên khi chiếu: ô SV không lộ tên, không có ô tìm tên", async () => {
    open("/gv/classes/c1/heatmap?tab=thong-ke");
    await screen.findByRole("list", { name: "Khung màu sinh viên" });
    expect(screen.getByLabelText("Lọc theo tên hoặc MSSV")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Ẩn tên khi chiếu/ }));
    await screen.findByLabelText("SV 01: 100% nút Đạt");
    expect(screen.queryByLabelText("Lọc theo tên hoặc MSSV")).toBeNull();
    expect(screen.queryByText(/Sinh viên 1/)).toBeNull();
  });
});
