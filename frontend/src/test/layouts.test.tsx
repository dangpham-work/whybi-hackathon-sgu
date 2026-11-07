import { render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { NAV } from "../lib/nav";
import { routes } from "../router";

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
});
