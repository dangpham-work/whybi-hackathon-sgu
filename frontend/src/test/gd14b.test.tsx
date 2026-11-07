import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { setToken } from "../lib/api";
import { auth } from "../lib/auth";
import { filenameFrom } from "../lib/download";
import { applyHeatmapEvent, type Snapshot } from "../lib/heatmap";
import { routes } from "../router";
import { err, mockApi, ok } from "./mock-api";

type Handler = (e: { channel: string; event: string; payload: unknown }) => void;
const handlers: Record<string, Handler> = {};
const push: Handler = (e) => handlers["class:c1:heatmap"]?.(e);
vi.mock("../lib/ws", async (orig) => ({
  ...(await orig<typeof import("../lib/ws")>()),
  useChannel: (c: string | null, h: Handler) => {
    if (c) handlers[c] = h;
    return "open";
  },
}));
vi.mock("../components/SkillTree", async (orig) => ({
  ...(await orig<typeof import("../components/SkillTree")>()),
  SkillTree: () => <div>cây</div>,
}));

const SNAP = {
  classId: "c1",
  enrolledCount: 2,
  onlineCount: 1,
  activeSessions: 0,
  nodes: [{ nodeId: "i5", nodeKey: "n5", code: "N5", title: "Con trỏ", color: "GREEN", passRate: 1, attemptedCount: 1, passedCount: 1, isRootCause: false }],
  grid: [{ studentId: "s1", studentName: "Trần Bảo Châu", studentCode: "3121001", states: {}, statesByKey: { n5: "MASTERED" }, progress: 1, masteredCount: 1 }],
  alerts: [],
  tree: { id: "v", versionNo: 1, status: "PUBLISHED", nodes: [], edges: [] },
} as unknown as Snapshot;
const lecturer = { "GET /me": ok({ id: "u", fullName: "GV", email: "g@x.vn", role: "LECTURER" }), "GET /notifications": ok([]) };
const open = () => render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/gv/classes/c1/heatmap"] })} />);
const lastUrl = (m: ReturnType<typeof mockApi>) => m.called("GET /classes/c1/heatmap").at(-1)!.url;
beforeEach(() => {
  auth.reset();
  setToken("acc-1");
});
afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

it("filenameFrom đọc tên tệp từ Content-Disposition", () => {
  expect(filenameFrom('attachment; filename="bao-cao.csv"', "x")).toBe("bao-cao.csv");
  expect(filenameFrom(null, "dự-phòng.pdf")).toBe("dự-phòng.pdf");
});

it("heatmap.cell khi ẩn danh không đưa tên / MSSV ra màn hình", () => {
  const payload = { studentId: "s9", studentName: "Lê Hoàng Dũng", studentCode: "3121009", nodeId: "i5", nodeKey: "n5", state: "IN_PROGRESS" };
  const open_ = applyHeatmapEvent(SNAP, { event: "heatmap.cell", payload });
  expect(open_.grid.at(-1)?.studentName).toBe("Lê Hoàng Dũng");
  const hidden = applyHeatmapEvent(SNAP, { event: "heatmap.cell", payload }, true);
  expect(hidden.grid.at(-1)).toMatchObject({ studentName: "", studentCode: "" });
});

describe("GV-05 lọc, tìm, trình chiếu, xuất báo cáo (GD-14, GD-16)", () => {
  it("tìm theo tên gửi q lên máy chủ sau khi gõ xong", async () => {
    const m = mockApi({ ...lecturer, "GET /classes/c1/heatmap": ok(SNAP) });
    open();
    fireEvent.change(await screen.findByLabelText(/Tìm sinh viên/), { target: { value: "Châu" } });
    await waitFor(() => expect(lastUrl(m)).toContain("q=Ch%C3%A2u"));
  });

  it("bật Ẩn tên khi chiếu thì lưới ẩn tên SV và gọi anonymize=true", async () => {
    const m = mockApi({ ...lecturer, "GET /classes/c1/heatmap": ok(SNAP) });
    open();
    fireEvent.click(await screen.findByRole("tab", { name: "Lưới SV × Nút" }));
    expect(await screen.findByText("Trần Bảo Châu")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Ẩn tên khi chiếu/ }));
    await waitFor(() => expect(lastUrl(m)).toContain("anonymize=true"));
    await waitFor(() => expect(screen.queryByText("Trần Bảo Châu")).toBeNull());
    expect(screen.getByText("SV 01")).toBeTruthy();
  });

  it("trình chiếu: toàn màn hình, ẩn tên bắt buộc, thoát được", async () => {
    const m = mockApi({ ...lecturer, "GET /classes/c1/heatmap": ok(SNAP) });
    open();
    fireEvent.click(await screen.findByRole("button", { name: /Trình chiếu/ }));
    const dlg = await screen.findByRole("dialog", { name: "Chế độ trình chiếu" });
    expect((within(dlg).getByRole("button", { name: /Ẩn tên khi chiếu/ }) as HTMLButtonElement).disabled).toBe(true);
    await waitFor(() => expect(lastUrl(m)).toContain("anonymize=true"));
    fireEvent.click(within(dlg).getByRole("button", { name: /Thoát trình chiếu/ }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Chế độ trình chiếu" })).toBeNull());
  });

  it("xuất báo cáo CSV: tải bằng token và lưu đúng tên tệp", async () => {
    mockApi({ ...lecturer, "GET /classes/c1/heatmap": ok(SNAP) });
    open();
    await screen.findByRole("button", { name: /Xuất CSV/ });
    const fetchReport = vi.fn(async () => new Response(new Blob(["a,b"]), { status: 200, headers: { "Content-Disposition": 'attachment; filename="lop-c1.csv"' } }));
    vi.stubGlobal("fetch", fetchReport);
    URL.createObjectURL = vi.fn(() => "blob:r");
    URL.revokeObjectURL = vi.fn();
    const saved: string[] = [];
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      saved.push(this.download);
    });
    fireEvent.click(screen.getByRole("button", { name: /Xuất CSV/ }));
    await waitFor(() => expect(saved).toEqual(["lop-c1.csv"]));
    const [path, init] = fetchReport.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/v1/classes/c1/report?format=csv");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer acc-1");
    click.mockRestore();
  });

  it("xuất báo cáo lỗi (lớp chưa phát hành cây) thì báo, không tải", async () => {
    mockApi({ ...lecturer, "GET /classes/c1/heatmap": ok(SNAP) });
    open();
    await screen.findByRole("button", { name: /Xuất PDF/ });
    vi.stubGlobal("fetch", vi.fn(async () => err(404, "TREE_NOT_PUBLISHED")));
    fireEvent.click(screen.getByRole("button", { name: /Xuất PDF/ }));
    expect(await screen.findByRole("alert")).toBeTruthy();
  });

  it("vẫn nhận sự kiện realtime khi đang trình chiếu", async () => {
    mockApi({ ...lecturer, "GET /classes/c1/heatmap": ok(SNAP) });
    open();
    fireEvent.click(await screen.findByRole("tab", { name: "Lưới SV × Nút" }));
    await screen.findByText("Trần Bảo Châu");
    act(() => push({ channel: "x", event: "heatmap.cell", payload: { studentId: "s1", studentName: "x", nodeId: "i5", nodeKey: "n5", state: "NOT_PASSED" } }));
    expect(await screen.findByLabelText("Chưa đạt")).toBeTruthy();
  });
});
