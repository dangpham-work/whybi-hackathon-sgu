import { configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
import "./reactflow-setup";

const STUDENT = { id: "u-sv", fullName: "Trần Bảo Châu", email: "sv02@whybi.test", role: "STUDENT" };
const TOKENS = { accessToken: "acc-1", refreshToken: "ref-1", tokenType: "bearer", expiresIn: 1800 };
const CTDL = { id: CLASS_ID, name: "CTDL&GT – Nhóm 02", semester: "HK1 2026–2027", joinCode: "CTDL2026", studentCount: 42, treeStatus: "PUBLISHED" };
const CREATED = { sessionId: "s-new", status: "EXPLAINING", opening: { text: "Con trỏ là gì vậy bạn?" } };

function open(url = `/sv/classes/${CLASS_ID}`) {
  const router = createMemoryRouter(routes, { initialEntries: [url] });
  render(<RouterProvider router={router} />);
  return router;
}

beforeEach(() => {
  auth.reset();
  setToken("acc-1");
});
afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

describe("SV-02 Bản đồ học tập (GD-06, FR-TB-01)", () => {
  it("gọi GET /classes/{id}/my-map và hiện tiến độ mastered/total", async () => {
    const api = mockApi({ [`GET /classes/${CLASS_ID}/my-map`]: ok(myMap()) });
    open();
    expect(await screen.findByText("4/11 nút")).toBeTruthy();
    expect(screen.getByRole("progressbar", { name: "Tiến độ của bạn" }).getAttribute("aria-valuenow")).toBe("4");
    expect(screen.getByText("Còn 7 nút để hoàn thành môn học")).toBeTruthy();
    expect(api.called(`GET /classes/${CLASS_ID}/my-map`)).toHaveLength(1);
  });

  it("mỗi nút có biểu tượng + chữ trạng thái (không chỉ màu) và dẫn tới SV-03", async () => {
    mockApi({ [`GET /classes/${CLASS_ID}/my-map`]: ok(myMap()) });
    open();
    const list = await screen.findByRole("list", { name: "Cây kỹ năng của bạn" });
    const items = within(list).getAllByRole("link");
    expect(items).toHaveLength(11);
    const n5 = within(list).getByRole("link", { name: /N5 Con trỏ/ });
    expect(n5.textContent).toContain("Chưa đạt · cao nhất 58/100 · 1 lượt");
    expect(n5.textContent).toContain("Nên học tiếp");
    expect(n5.getAttribute("href")).toBe(`/sv/classes/${CLASS_ID}/nodes/${nodeIdOf("n5_con_tro")}`);
    expect(within(list).getByRole("link", { name: /N6 Cấp phát động/ }).textContent).toContain("Khóa · mở khi bạn Đạt N5");
    expect(n5.querySelector("svg")).toBeTruthy();
  });

  it("chuyển sang dạng sơ đồ dùng SkillTree (mode learner)", async () => {
    mockApi({ [`GET /classes/${CLASS_ID}/my-map`]: ok(myMap()) });
    open();
    fireEvent.click(await screen.findByRole("button", { name: "Sơ đồ" }));
    expect(await screen.findByLabelText("Cây kỹ năng")).toBeTruthy();
    expect(screen.getByLabelText(/Con trỏ – Chưa đạt/)).toBeTruthy();
  });

  it("cây chưa phát hành → câu dễ hiểu theo mã TREE_NOT_PUBLISHED", async () => {
    mockApi({ [`GET /classes/${CLASS_ID}/my-map`]: err(404, "TREE_NOT_PUBLISHED") });
    open();
    expect((await screen.findByRole("alert")).textContent).toContain("Giảng viên chưa phát hành cây kỹ năng");
  });

  it("backend còn 501 (C2-10) → hộp đang phát triển, vẫn có tiêu đề màn", async () => {
    mockApi({});
    open();
    expect(await screen.findByRole("heading", { name: "Bản đồ học tập" })).toBeTruthy();
    expect(await screen.findByText(/đang được phát triển/)).toBeTruthy();
  });

  it("nút 'Bắt đầu giảng' gọi POST /sessions {nodeId} rồi sang SV-04", async () => {
    const api = mockApi({ [`GET /classes/${CLASS_ID}/my-map`]: ok(myMap()), "POST /sessions": ok(CREATED, 201) });
    const router = open();
    fireEvent.click(await screen.findByRole("button", { name: /Bắt đầu giảng N5/ }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/sv/sessions/s-new"));
    expect(api.called("POST /sessions")[0].body).toEqual({ nodeId: nodeIdOf("n5_con_tro"), inputMode: "TEXT", ttsEnabled: false });
  });

  it("không có nút nào bắt đầu được thì không hiện nút học tiếp", async () => {
    mockApi({ [`GET /classes/${CLASS_ID}/my-map`]: ok(myMap({ n5_con_tro: { canStart: false } })) });
    open();
    await screen.findByText("4/11 nút");
    expect(screen.queryByRole("button", { name: /Bắt đầu giảng/ })).toBeNull();
  });
});

describe("Xong khi GD-06: từ đăng nhập đến bắt đầu phiên không quá 3 thao tác (NFR-11)", () => {
  it("1) đăng nhập → 2) chọn lớp → 3) Bắt đầu giảng ⇒ POST /sessions", async () => {
    setToken(null);
    const api = mockApi({
      "POST /auth/login": ok(TOKENS),
      "GET /me": ok(STUDENT),
      "GET /classes": ok([CTDL]),
      [`GET /classes/${CLASS_ID}/my-map`]: ok(myMap()),
      "POST /sessions": ok(CREATED, 201),
    });
    const router = open("/login");
    let actions = 0;

    fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "sv02@whybi.test" } });
    fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "Whybi@2026" } });
    fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
    actions++;

    const list = await screen.findByRole("list", { name: "Lớp của bạn" });
    fireEvent.click(within(list).getByRole("link", { name: /CTDL&GT – Nhóm 02/ }));
    actions++;

    fireEvent.click(await screen.findByRole("button", { name: /Bắt đầu giảng N5/ }));
    actions++;

    await waitFor(() => expect(router.state.location.pathname).toBe("/sv/sessions/s-new"));
    expect(api.called("POST /sessions")).toHaveLength(1);
    expect(actions).toBeLessThanOrEqual(3);
  });
});
