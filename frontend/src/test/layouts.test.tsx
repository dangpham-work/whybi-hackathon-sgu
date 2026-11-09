import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { getToken, setToken } from "../lib/api";
import { auth } from "../lib/auth";
import { NAV } from "../lib/nav";
import { routes } from "../router";
import { mockApi, ok } from "./mock-api";

const menuOf = async (url: string) => {
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [url] })} />);
  const nav = await screen.findByRole("navigation", { name: "Điều hướng chính" });
  return within(nav)
    .getAllByRole("listitem")
    .map((li) => li.textContent?.trim());
};

describe("layout hiển thị điều hướng đúng vai (GD-01)", () => {
  it("Giảng viên thấy menu GV theo sơ đồ 5.5.1", async () => {
    const items = await menuOf("/gv/classes/demo");
    expect(items).toEqual(["Lớp của tôi", "Cây kỹ năng", "Bản đồ nhiệt", "Ghép cặp", "Cấu hình"]);
  });

  it("GV chưa chọn lớp: mục theo lớp bị khóa, có lời nhắc", async () => {
    await menuOf("/gv/classes");
    const tree = screen.getByText("Cây kỹ năng").closest("[aria-disabled]");
    expect(tree?.getAttribute("aria-disabled")).toBe("true");
    expect(tree?.getAttribute("title")).toBe("Chọn một lớp trước");
  });

  it("GV trong một lớp: link trỏ đúng màn của lớp", async () => {
    await menuOf("/gv/classes/abc");
    expect(screen.getByRole("link", { name: /Bản đồ nhiệt/ }).getAttribute("href")).toBe("/gv/classes/abc/heatmap");
    expect(screen.getByRole("link", { name: /Ghép cặp/ }).getAttribute("href")).toBe("/gv/classes/abc/matching");
  });

  it("chỉ mục của nhánh đang mở được đánh dấu (GV-06 thuộc Bản đồ nhiệt)", async () => {
    await menuOf("/gv/classes/abc/nodes/n5");
    const current = screen.getAllByRole("link").filter((a) => a.getAttribute("aria-current") === "page");
    expect(current.map((a) => a.textContent?.trim())).toEqual(["Bản đồ nhiệt"]);
  });

  it("Sinh viên thấy thanh tab dưới", async () => {
    const items = await menuOf("/sv/classes/abc");
    expect(items).toEqual(["Bản đồ", "Bạn cùng tiến", "Lịch sử", "Hồ sơ"]);
    expect(screen.getByRole("link", { name: /Bạn cùng tiến/ }).getAttribute("href")).toBe("/sv/classes/abc/peers");
  });

  it("Quản trị viên thấy menu quản trị", async () => {
    const items = await menuOf("/admin/users");
    expect(items).toEqual(NAV.ADMIN().map((i) => i.label));
    expect(items).toContain("Cấu hình nhà cung cấp AI");
  });

  it("menu mỗi vai không lẫn mục của vai khác", () => {
    const gv = NAV.LECTURER("x").map((i) => i.label);
    const sv = NAV.STUDENT("x").map((i) => i.label);
    const ad = NAV.ADMIN().map((i) => i.label);
    expect(gv.filter((l) => sv.includes(l) || ad.includes(l))).toEqual([]);
    expect(sv.filter((l) => ad.includes(l))).toEqual([]);
  });

  it("mọi mục menu đều có biểu tượng", () => {
    for (const item of [...NAV.LECTURER("x"), ...NAV.STUDENT("x"), ...NAV.ADMIN()]) expect(item.icon).toBeTruthy();
  });

  it.each(["/gv/classes/demo", "/admin/users"])(
    "khung %s: header dính khi cuộn, không bị kéo theo cùng nội dung",
    async (url) => {
      // header đầu tiên trong DOM luôn là header của KHUNG (trước <main>) – trang bên trong (AdminPage) cũng
      // có <header> riêng cho tiêu đề, không lấy nhầm cái đó.
      const { container } = render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [url] })} />);
      const header = container.querySelector("header");
      expect(header?.className).toMatch(/sticky/);
      expect(header?.className).toMatch(/top-0/);
    },
  );

  it("QTV: có nút Quay lại ở màn không phải trang chủ (AD-02), không có ở trang chủ (AD-01)", async () => {
    const r1 = render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/admin/users"] })} />);
    const header1 = r1.container.querySelector("header")!;
    expect(within(header1).queryByRole("button", { name: "Quay lại" })).toBeNull();
    r1.unmount();

    const r2 = render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/admin/courses"] })} />);
    const header2 = r2.container.querySelector("header")!;
    expect(await within(header2).findByRole("button", { name: "Quay lại" })).toBeTruthy();
    r2.unmount();
  });

  it.each(["/gv/classes", "/sv/classes/abc", "/admin/users"])(
    "khung %s có nút Đăng xuất; bấm vào thì xóa phiên và về trang đăng nhập (#195)",
    async (url) => {
      auth.reset();
      setToken("tok-195");
      const m = mockApi({ "POST /auth/logout": ok(undefined, 204) });
      const router = createMemoryRouter(routes, { initialEntries: [url] });
      render(<RouterProvider router={router} />);
      const btn = await screen.findByRole("button", { name: /Đăng xuất/ });
      fireEvent.click(btn);
      await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
      expect(getToken()).toBeNull();
      expect(m.called("POST /auth/logout")).toHaveLength(1);
    },
  );
});
