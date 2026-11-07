import { fireEvent, render, screen } from "@testing-library/react";
import { AsyncView } from "../components/AsyncView";
import { ApiError } from "../lib/api";
import { useApi } from "../lib/useApi";

function Demo({ load }: { load: (signal: AbortSignal) => Promise<string[]> }) {
  const state = useApi(load, []);
  return <AsyncView state={state}>{(items) => <ul>{items.map((i) => <li key={i}>{i}</li>)}</ul>}</AsyncView>;
}

describe("trạng thái tải và lỗi dùng chung (GD-02)", () => {
  it("hiện 'Đang tải…' rồi tới dữ liệu", async () => {
    render(<Demo load={() => Promise.resolve(["N1 Biến", "N2 Mảng"])} />);
    expect(screen.getByRole("status").textContent).toContain("Đang tải");
    expect(await screen.findByText("N2 Mảng")).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("lỗi API hiện câu dễ hiểu kèm nút Thử lại; bấm thì gọi lại", async () => {
    const load = vi
      .fn<(s: AbortSignal) => Promise<string[]>>()
      .mockRejectedValueOnce(new ApiError(403, "FORBIDDEN"))
      .mockResolvedValueOnce(["N5 Con trỏ"]);
    render(<Demo load={load} />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Bạn không có quyền xem nội dung này.");
    expect(alert.querySelector("svg")).toBeTruthy(); // màu đỏ luôn kèm biểu tượng
    fireEvent.click(screen.getByRole("button", { name: "Thử lại" }));
    expect(await screen.findByText("N5 Con trỏ")).toBeTruthy();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("501 hiện 'đang phát triển' (không phải lỗi đỏ, không giả lập dữ liệu)", async () => {
    render(<Demo load={() => Promise.reject(new ApiError(501, "NOT_IMPLEMENTED", undefined, { card: "C2-13" }))} />);
    const box = await screen.findByText(/Chức năng đang được phát triển \(thẻ C2-13\)/);
    expect(box).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("401 (chưa / hết đăng nhập) mời đăng nhập lại và quay về đúng trang", async () => {
    window.history.pushState({}, "", "/sv/classes");
    render(<Demo load={() => Promise.reject(new ApiError(401, "UNAUTHORIZED"))} />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Phiên đăng nhập đã hết hạn");
    expect(screen.getByRole("link", { name: "Đăng nhập lại" }).getAttribute("href")).toBe("/login?next=%2Fsv%2Fclasses");
    expect(screen.queryByRole("button", { name: "Thử lại" })).toBeNull();
  });

  it("lỗi không phải ApiError vẫn hiện câu chung, không lộ chi tiết kỹ thuật", async () => {
    render(<Demo load={() => Promise.reject(new Error("TypeError: x is undefined"))} />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Có lỗi xảy ra, vui lòng thử lại.");
    expect(alert.textContent).not.toContain("undefined");
  });

  it("dữ liệu rỗng hiện thông báo trống nếu được cấu hình", async () => {
    function Empty() {
      const state = useApi(() => Promise.resolve([] as string[]), []);
      return (
        <AsyncView state={state} isEmpty={(d) => d.length === 0} empty="Chưa có lớp nào">
          {() => <p>có dữ liệu</p>}
        </AsyncView>
      );
    }
    render(<Empty />);
    expect(await screen.findByText("Chưa có lớp nào")).toBeTruthy();
  });

  it("hủy yêu cầu cũ khi component bị gỡ", () => {
    let signal: AbortSignal | undefined;
    const { unmount } = render(
      <Demo
        load={(s) => {
          signal = s;
          return new Promise(() => {});
        }}
      />,
    );
    unmount();
    expect(signal?.aborted).toBe(true);
  });
});
