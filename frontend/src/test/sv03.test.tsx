import { act, configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { setToken } from "../lib/api";
import { auth } from "../lib/auth";
import { routes } from "../router";
import { CLASS_ID, myMap, nodeIdOf } from "./fixtures/my-map";
import { err, mockApi, ok } from "./mock-api";
// Router nạp màn kiểu lazy (+ React Flow): nạp sẵn và nới thời gian chờ findBy* khi cả bộ test chạy song song
import "../pages/student/SV02";
import "../pages/student/SV03";

configure({ asyncUtilTimeout: 4000 });

const MAP = `GET /classes/${CLASS_ID}/my-map`;
const CREATED = { sessionId: "s-new", status: "EXPLAINING", opening: { text: "Con trỏ là gì vậy bạn?" } };

function open(key = "n5_con_tro") {
  const router = createMemoryRouter(routes, { initialEntries: [`/sv/classes/${CLASS_ID}/nodes/${nodeIdOf(key)}`] });
  render(<RouterProvider router={router} />);
  return router;
}
const startButton = () => screen.findByRole("button", { name: "Bắt đầu giảng cho AI" });

beforeEach(() => {
  auth.reset();
  setToken("acc-1");
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  setToken(null);
});

describe("SV-03 Chi tiết nút (GD-06, FR-TB-02)", () => {
  it("hiện ngưỡng và số câu theo rubric, kèm đủ điều kiện Đạt BR-03", async () => {
    const data = myMap();
    data.tree = { ...data.tree, nodes: data.tree.nodes.map((n) => n.rubric ? {
      ...n, rubric: { ...n.rubric, passThreshold: 85, minChallenges: 5, minPassedChallenges: 4 },
    } : n) };
    mockApi({ [MAP]: ok(data) });
    open();
    const state = await screen.findByRole("region", { name: "Trạng thái nút" });
    expect(within(state).getByText("85")).toBeTruthy();
    expect(within(state).getByText("≥ 5")).toBeTruthy();
    expect(screen.getByText(/≥ 85 điểm.*≥ 4 câu phản biện/)).toBeTruthy();
    expect(screen.getByText(/đủ ý bắt buộc.*sửa.*quan niệm sai nghiêm trọng/i)).toBeTruthy();
  });

  it("không có rubric thì không tự khẳng định ngưỡng Đạt", async () => {
    mockApi({ [MAP]: ok(myMap()) });
    open("n1_bien_bo_nho");
    const state = await screen.findByRole("region", { name: "Trạng thái nút" });
    expect(within(state).queryByText("70")).toBeNull();
    expect(screen.queryByText(/bạn có thể bắt đầu ngay/)).toBeNull();
  });

  it("đổi nút không giữ lỗi và link phiên của nút trước", async () => {
    mockApi({
      [MAP]: ok(myMap({ n6_cap_phat_dong: { state: "AVAILABLE", canStart: true, missingPrerequisites: [] } })),
      "POST /sessions": err(409, "SESSION_IN_PROGRESS", "x", { sessionId: "s-old-node" }),
    });
    const router = open();
    fireEvent.click(await startButton());
    await screen.findByRole("link", { name: "Tiếp tục phiên đang giảng" });
    await act(() => router.navigate(`/sv/classes/${CLASS_ID}/nodes/${nodeIdOf("n6_cap_phat_dong")}`));
    await screen.findByRole("heading", { name: /N6 — Cấp phát động/ });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("link", { name: "Tiếp tục phiên đang giảng" })).toBeNull();
  });

  it.each(["bản đồ", "chi tiết"])("%s: hết thời gian chờ thì hỏi lại máy chủ để bật bắt đầu", async (page) => {
    const now = Date.now();
    const retryAt = new Date(now + 60_000).toISOString();
    const timeout = vi.spyOn(globalThis, "setTimeout");
    let expired = false;
    const api = mockApi({ [MAP]: () => ok(myMap({ n5_con_tro: expired ? {
      canStart: true, retryAt: null,
    } : { canStart: false, retryAt } })) });
    const path = page === "bản đồ" ? `/sv/classes/${CLASS_ID}` : `/sv/classes/${CLASS_ID}/nodes/${nodeIdOf("n5_con_tro")}`;
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />);
    await screen.findByText(page === "bản đồ" ? "4/11 nút" : /Thử lại lúc/, {}, { timeout: 5000 });
    const scheduled = timeout.mock.calls.find(([, delay]) => typeof delay === "number" && delay > 50_000 && delay <= 60_000);
    expect(scheduled).toBeDefined();
    const callsBefore = api.called(MAP).length;
    expired = true;
    vi.spyOn(Date, "now").mockReturnValue(now + 60_001);
    await act(async () => { (scheduled![0] as () => void)(); });
    await waitFor(() => expect(api.called(MAP).length).toBeGreaterThan(callsBefore));
    const button = await screen.findByRole("button", { name: page === "bản đồ" ? /Bắt đầu giảng N5/ : "Bắt đầu giảng cho AI" });
    expect(button.hasAttribute("disabled")).toBe(false);
  });

  it("bản đồ không có nút: hiện trạng thái rỗng thay vì báo Đạt mọi nút", async () => {
    const data = myMap({}, { totalCount: 0, masteredCount: 0, progress: [], frontier: [] });
    data.tree = { ...data.tree, nodes: [], edges: [] };
    mockApi({ [MAP]: ok(data) });
    const router = open();
    await act(() => router.navigate(`/sv/classes/${CLASS_ID}`));
    expect(await screen.findByText(/Chưa có nút kỹ năng/)).toBeTruthy();
    expect(screen.queryByText("Bạn đã Đạt mọi nút của môn học")).toBeNull();
  });

  it("hiện tên nút, trạng thái (biểu tượng + chữ), điểm cao nhất và số lượt", async () => {
    mockApi({ [MAP]: ok(myMap()) });
    open();
    expect(await screen.findByRole("heading", { name: "N5 — Con trỏ" })).toBeTruthy();
    expect(screen.getByText("Chương 3 · Bloom: Hiểu")).toBeTruthy();
    const state = screen.getByRole("region", { name: "Trạng thái nút" });
    expect(within(state).getByText("Chưa đạt")).toBeTruthy();
    expect(within(state).getByText("58")).toBeTruthy();
    expect(within(state).getByText("điểm cao nhất")).toBeTruthy();
    expect(within(state).getByText("Lượt 1")).toBeTruthy();
  });

  it("liệt kê tiên quyết kèm trạng thái; đủ điều kiện thì bật nút bắt đầu", async () => {
    mockApi({ [MAP]: ok(myMap()) });
    open();
    expect(await screen.findByText("Đủ điều kiện bắt đầu")).toBeTruthy();
    const pre = screen.getByRole("list", { name: "Nút tiên quyết" });
    expect(within(pre).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      expect.stringContaining("N1"),
      expect.stringContaining("N3"),
    ]);
    expect(within(pre).getAllByText("Đạt")).toHaveLength(2);
    expect((await startButton()).hasAttribute("disabled")).toBe(false);
  });

  it("nút khóa: ghi rõ tiên quyết còn thiếu và tắt nút bắt đầu", async () => {
    mockApi({ [MAP]: ok(myMap()) });
    open("n6_cap_phat_dong");
    expect(await screen.findByText("Còn thiếu tiên quyết: N5 Con trỏ")).toBeTruthy();
    expect((await startButton()).hasAttribute("disabled")).toBe(true);
  });

  it("vừa Chưa đạt, đang chờ BR-11 → báo giờ được thử lại", async () => {
    const later = new Date(Date.now() + 5 * 60_000).toISOString();
    mockApi({ [MAP]: ok(myMap({ n5_con_tro: { retryAt: later, canStart: false } })) });
    open();
    expect(await screen.findByText(/Thử lại lúc \d{2}:\d{2}/)).toBeTruthy();
    expect((await startButton()).hasAttribute("disabled")).toBe(true);
  });

  it("bấm bắt đầu → POST /sessions {nodeId} → SV-04", async () => {
    const api = mockApi({ [MAP]: ok(myMap()), "POST /sessions": ok(CREATED, 201) });
    const router = open();
    fireEvent.click(await startButton());
    await waitFor(() => expect(router.state.location.pathname).toBe("/sv/sessions/s-new"));
    expect(api.called("POST /sessions")[0].body).toMatchObject({ nodeId: nodeIdOf("n5_con_tro") });
  });

  it("POST /sessions trả 409 SESSION_IN_PROGRESS → mời tiếp tục phiên đang có", async () => {
    mockApi({ [MAP]: ok(myMap()), "POST /sessions": err(409, "SESSION_IN_PROGRESS", "x", { sessionId: "s-run" }) });
    open();
    fireEvent.click(await startButton());
    const link = await screen.findByRole("link", { name: "Tiếp tục phiên đang giảng" });
    expect(link.getAttribute("href")).toBe("/sv/sessions/s-run");
  });

  it("POST /sessions trả 409 NODE_LOCKED → câu dễ hiểu", async () => {
    mockApi({ [MAP]: ok(myMap()), "POST /sessions": err(409, "NODE_LOCKED", "x", { missingPrerequisites: ["n3_ham_tham_so"] }) });
    open();
    fireEvent.click(await startButton());
    expect((await screen.findByRole("alert")).textContent).toContain("Nút này đang khóa");
  });

  it("POST /sessions trả 409 NODE_ALREADY_MASTERED (C2-10) → câu dễ hiểu, không phải câu chung", async () => {
    mockApi({ [MAP]: ok(myMap()), "POST /sessions": err(409, "NODE_ALREADY_MASTERED") });
    open();
    fireEvent.click(await startButton());
    expect((await screen.findByRole("alert")).textContent).toContain("Bạn đã Đạt nút này rồi – hãy chọn nút khác để học tiếp.");
  });

  it("POST /sessions còn 501 (C1-07) → báo đang phát triển, không giả lập", async () => {
    mockApi({ [MAP]: ok(myMap()) });
    open();
    fireEvent.click(await startButton());
    expect(await screen.findByText(/đang được phát triển/)).toBeTruthy();
  });

  it("nút không có trong bản đồ → báo không tìm thấy, có đường quay lại SV-02", async () => {
    mockApi({ [MAP]: ok(myMap()) });
    open("khong_co");
    expect(await screen.findByText(/Không tìm thấy nút này/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Quay lại bản đồ học tập" }).getAttribute("href")).toBe(`/sv/classes/${CLASS_ID}`);
  });
});
