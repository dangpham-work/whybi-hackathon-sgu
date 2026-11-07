import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { setToken } from "../lib/api";
import { auth } from "../lib/auth";
import { routes } from "../router";
import { err, mockApi, ok } from "./mock-api";

const CTDL = { id: "0fcd3055-a08a-5a08-b881-bbab21c660c2", name: "CTDL&GT – Nhóm 02", semester: "HK1 2026–2027", joinCode: "CTDL2026", studentCount: 42, treeStatus: "PUBLISHED" };
const LTC = { id: "c-ltc", name: "Lập trình C – Nhóm 05", semester: "HK1 2026–2027", joinCode: "W3X8NB1D", studentCount: 38, treeStatus: null };

function open() {
  const router = createMemoryRouter(routes, { initialEntries: ["/sv/classes"] });
  render(<RouterProvider router={router} />);
  return router;
}
const codeBoxes = async () => {
  const group = await screen.findByRole("group", { name: "Mã tham gia 8 ký tự" });
  return within(group).getAllByRole("textbox");
};
const joinButton = () => screen.getByRole("button", { name: "Tham gia lớp" });

beforeEach(() => {
  auth.reset();
  setToken("acc-1");
});
afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

describe("SV-01 Danh sách lớp / nhập mã (GD-04)", () => {
  it("chào theo tên và liệt kê lớp của SV", async () => {
    mockApi({ "GET /me": ok({ id: "u", fullName: "Trần Bảo Châu", email: "a@b.vn", role: "STUDENT" }), "GET /classes": ok([CTDL, LTC]) });
    open();
    expect(await screen.findByRole("heading", { name: "Chào Bảo Châu," })).toBeTruthy();
    const list = await screen.findByRole("list", { name: "Lớp của bạn" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).getByRole("link", { name: /CTDL&GT – Nhóm 02/ }).getAttribute("href")).toBe(`/sv/classes/${CTDL.id}`);
    expect(within(list).getByText(/42 SV/)).toBeTruthy();
    expect(screen.getByText("2 lớp")).toBeTruthy();
  });

  it("chưa có lớp nào thì nhắc nhập mã", async () => {
    mockApi({ "GET /classes": ok([]) });
    open();
    expect(await screen.findByText(/Bạn chưa tham gia lớp nào/)).toBeTruthy();
  });

  it("có 8 ô mã; nút Tham gia chỉ bật khi đủ 8 ký tự", async () => {
    mockApi({ "GET /classes": ok([]) });
    open();
    const boxes = await codeBoxes();
    expect(boxes).toHaveLength(8);
    expect(joinButton().hasAttribute("disabled")).toBe(true);
    fireEvent.change(boxes[0], { target: { value: "CTDL202" } });
    expect(joinButton().hasAttribute("disabled")).toBe(true);
    fireEvent.change(boxes[7], { target: { value: "6" } });
    expect(joinButton().hasAttribute("disabled")).toBe(false);
  });

  it("Xong khi: SV nhập mã 8 ký tự là vào được lớp (dán chữ thường, có dấu cách)", async () => {
    const api = mockApi({ "GET /classes": ok([]), "POST /classes/join": ok(CTDL) });
    const router = open();
    const boxes = await codeBoxes();
    fireEvent.change(boxes[0], { target: { value: "ctdl 2026" } });
    expect(boxes.map((b) => (b as HTMLInputElement).value).join("")).toBe("CTDL2026");
    fireEvent.click(joinButton());
    await waitFor(() => expect(router.state.location.pathname).toBe(`/sv/classes/${CTDL.id}`));
    expect(api.called("POST /classes/join")[0].body).toEqual({ joinCode: "CTDL2026" });
    expect(await screen.findByRole("heading", { name: "Bản đồ học tập" })).toBeTruthy();
  });

  it("Enter ở ô cuối cũng gửi mã", async () => {
    const api = mockApi({ "GET /classes": ok([]), "POST /classes/join": ok(CTDL) });
    open();
    const boxes = await codeBoxes();
    fireEvent.change(boxes[0], { target: { value: "CTDL2026" } });
    fireEvent.submit(boxes[7].closest("form")!);
    await waitFor(() => expect(api.called("POST /classes/join")).toHaveLength(1));
  });

  it("Backspace ở ô trống lùi về ô trước và xóa", async () => {
    mockApi({ "GET /classes": ok([]) });
    open();
    const boxes = await codeBoxes();
    fireEvent.change(boxes[0], { target: { value: "AB" } });
    fireEvent.keyDown(boxes[2], { key: "Backspace" });
    expect((boxes[1] as HTMLInputElement).value).toBe("");
    expect(document.activeElement).toBe(boxes[1]);
  });

  it.each([
    [404, "JOIN_CODE_INVALID", "Không tìm thấy lớp với mã này. Kiểm tra lại mã giảng viên cung cấp."],
    [409, "ALREADY_ENROLLED", "Bạn đã ở trong lớp này rồi."],
    [422, "VALIDATION_ERROR", "Mã tham gia gồm đúng 8 chữ hoặc số."],
    [403, "FORBIDDEN", "Chỉ tài khoản sinh viên mới tham gia lớp bằng mã."],
  ])("mã lỗi %i %s hiện câu dễ hiểu và giữ nguyên mã đã nhập", async (status, code, text) => {
    mockApi({ "GET /classes": ok([]), "POST /classes/join": err(status, code) });
    open();
    const boxes = await codeBoxes();
    fireEvent.change(boxes[0], { target: { value: "ZZZZ9999" } });
    fireEvent.click(joinButton());
    expect((await screen.findByRole("alert")).textContent).toContain(text);
    expect(boxes.map((b) => (b as HTMLInputElement).value).join("")).toBe("ZZZZ9999");
  });

  it("danh sách lớp chưa có API (501) vẫn cho nhập mã", async () => {
    mockApi({ "GET /classes": err(501, "NOT_IMPLEMENTED", "x", { card: "C2-08" }) });
    open();
    expect(await screen.findByText("Chức năng đang được phát triển (thẻ C2-08).")).toBeTruthy();
    expect(await codeBoxes()).toHaveLength(8);
  });
});
