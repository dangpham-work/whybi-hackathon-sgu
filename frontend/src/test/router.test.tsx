import { render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider, type RouteObject } from "react-router";
import { ScreenPlaceholder } from "../components/ScreenPlaceholder";
import { routes } from "../router";
import { SCREENS } from "../screens";

/** Gom mọi path (kể cả route con trong layout) của cây route. */
function allPaths(rs: RouteObject[]): string[] {
  return rs.flatMap((r) => [...(r.path ? [r.path] : []), ...(r.children ? allPaths(r.children) : [])]);
}

const open = (url: string) => render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [url] })} />);

describe("router tự nạp (GD-01)", () => {
  it("có route cho đủ mọi màn trong src/screens.ts", () => {
    const paths = allPaths(routes);
    for (const s of SCREENS) expect(paths).toContain(s.path);
  });

  it("trang giữ chỗ hiện đúng mã màn (không phụ thuộc màn nào đã dựng)", () => {
    const gv = SCREENS.find((x) => x.code === "GV-05")!;
    render(<ScreenPlaceholder screen={gv} />);
    expect(screen.getByRole("heading", { name: gv.title })).toBeTruthy();
    expect(screen.getByText(/GV-05 · Vòng 1 · Thẻ GD-10/)).toBeTruthy();
  });

  it("màn có file pages/<vai>/<MÃ>.tsx được nạp tự động (AUTH-01)", async () => {
    open("/login");
    expect(await screen.findByRole("button", { name: "Đăng nhập" })).toBeTruthy();
  });

  it("đường dẫn lạ hiện trang không tìm thấy", async () => {
    open("/khong-co-trang-nay");
    expect(await screen.findByRole("heading", { name: /Không tìm thấy trang/ })).toBeTruthy();
  });

  it("breadcrumb GV hiện tên màn đang mở", async () => {
    open("/gv/classes/demo/tree");
    const crumbs = await screen.findByRole("navigation", { name: "Đường dẫn" });
    expect(within(crumbs).getByText("Lớp của tôi")).toBeTruthy();
    expect(within(crumbs).getByText("Trình sửa cây & rubric")).toBeTruthy();
  });
});
