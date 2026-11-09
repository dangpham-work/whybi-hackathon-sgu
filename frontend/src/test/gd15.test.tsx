import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { setToken } from "../lib/api";
import { auth } from "../lib/auth";
import { routes } from "../router";
import { err, mockApi, ok } from "./mock-api";

let push: (e: { channel: string; event: string; payload: unknown }) => void = () => {};
vi.mock("../lib/ws", async (orig) => ({
  ...(await orig<typeof import("../lib/ws")>()),
  useChannel: (_ch: string | null, h: typeof push) => {
    push = h;
    return "open";
  },
}));

const admin = { "GET /me": ok({ id: "ad", fullName: "QTV", email: "a@x.vn", role: "ADMIN" }), "GET /notifications": ok([]) };
const open = (url: string) => render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [url] })} />);
beforeEach(() => {
  auth.reset();
  setToken("acc-1");
});
afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});
const USER = { id: "u1", fullName: "Lê Hoàng Dũng", email: "d@x.vn", role: "STUDENT", isActive: true, studentCode: "3121002", createdAt: "" };

describe("AD-01 Tài khoản (GD-15)", () => {
  it("liệt kê, khóa tài khoản và đặt lại mật khẩu (hiện mật khẩu một lần)", async () => {
    const m = mockApi({
      ...admin,
      "GET /admin/users": ok([USER]),
      "PATCH /admin/users/u1": ok({ ...USER, isActive: false }),
      "POST /admin/users/u1/reset-password": ok({ user: USER, password: "Xk9-abc" }),
    });
    open("/admin/users");
    fireEvent.click(await screen.findByRole("button", { name: "Khóa Lê Hoàng Dũng" }));
    await waitFor(() => expect(m.called("PATCH /admin/users/u1")).toHaveLength(1));
    expect(m.called("PATCH /admin/users/u1")[0].body).toEqual({ isActive: false });
    fireEvent.click(screen.getByRole("button", { name: "Đặt lại mật khẩu Lê Hoàng Dũng" }));
    expect(await screen.findByText("Xk9-abc")).toBeTruthy();
  });

  it("tạo tài khoản SV gửi MSSV; trùng thì báo câu dễ hiểu", async () => {
    const m = mockApi({ ...admin, "GET /admin/users": ok([]), "POST /admin/users": err(409, "USER_EXISTS") });
    open("/admin/users");
    const form = (await screen.findByRole("region", { name: "Tạo tài khoản" })) as HTMLElement;
    fireEvent.change(within(form).getByLabelText("Họ tên"), { target: { value: "An" } });
    fireEvent.change(within(form).getByLabelText("Email"), { target: { value: "an@x.vn" } });
    fireEvent.change(within(form).getByLabelText("MSSV"), { target: { value: "3121009" } });
    fireEvent.click(within(form).getByRole("button", { name: /Tạo tài khoản/ }));
    expect(await screen.findByText(/đã có tài khoản/)).toBeTruthy();
    expect(m.called("POST /admin/users")[0].body).toMatchObject({ role: "STUDENT", studentCode: "3121009" });
  });

  it("nhập CSV báo số tạo / bỏ qua / lỗi", async () => {
    mockApi({
      ...admin,
      "GET /admin/users": ok([]),
      "POST /admin/users/import": ok({ created: [{ row: 2, studentCode: "1", fullName: "A", email: "a@x.vn", password: "p1" }], skipped: [{ row: 3, reason: "đã có" }], errors: [{ row: 4, reason: "thiếu email" }] }, 201),
    });
    open("/admin/users");
    fireEvent.change(await screen.findByLabelText("Chọn tệp CSV"), { target: { files: [new File(["x"], "sv.csv")] } });
    fireEvent.click(screen.getByRole("button", { name: /Nhập danh sách/ }));
    expect((await screen.findByRole("status")).textContent).toMatch(/Đã tạo 1 · bỏ qua 1 · lỗi 1/);
    expect(screen.getByText(/dòng 4: thiếu email/)).toBeTruthy();
  });
});

describe("AD-02 Môn học, AD-04 Hạn mức, AD-05 Cờ (GD-15)", () => {
  it("thêm môn học và hiển thị nút chép mã môn", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    const m = mockApi({ ...admin, "GET /admin/courses": ok([]), "POST /admin/courses": ok({ id: "uuid-ctdl-123", code: "CTDL", name: "Cấu trúc dữ liệu", credits: 3 }, 201) });
    open("/admin/courses");
    fireEvent.change(await screen.findByLabelText("Mã môn"), { target: { value: "CTDL" } });
    fireEvent.change(screen.getByLabelText("Tên môn"), { target: { value: "Cấu trúc dữ liệu" } });
    fireEvent.change(screen.getByLabelText("Số tín chỉ"), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: /Thêm môn/ }));
    await waitFor(() => expect(m.called("POST /admin/courses")).toHaveLength(1));
    expect(m.called("POST /admin/courses")[0].body).toMatchObject({ code: "CTDL", name: "Cấu trúc dữ liệu", credits: 3 });

    // Kiểm tra thông báo kết quả tạo môn kèm nút copy
    const status = await screen.findByRole("status", { name: "Kết quả tạo môn" });
    expect(status.textContent).toContain("Cấu trúc dữ liệu");
    const copyBtn = within(status).getByRole("button", { name: "Chép mã CTDL" });
    await act(async () => {
      fireEvent.click(copyBtn);
    });
    expect(writeText).toHaveBeenCalledWith("uuid-ctdl-123");
  });

  it("thanh môn học theo từng hàng có nút copy mã môn không lộ chuỗi UUID", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    const courses = [
      { id: "uuid-comp1013", code: "COMP1013", name: "Cấu trúc dữ liệu & Giải thuật", credits: 4, description: null },
      { id: "uuid-comp2031", code: "COMP2031", name: "Hệ điều hành", credits: 3, description: null },
    ];
    mockApi({ ...admin, "GET /admin/courses": ok(courses) });
    open("/admin/courses");
    const table = await screen.findByRole("table", { name: "Môn học" });
    // Không hiện chuỗi UUID trên giao diện
    expect(within(table).queryByText("uuid-comp1013")).toBeNull();
    expect(within(table).queryByText("uuid-comp2031")).toBeNull();

    // Có nút copy mã môn cho từng dòng
    const copyBtn1 = within(table).getByRole("button", { name: "Chép mã môn COMP1013" });
    const copyBtn2 = within(table).getByRole("button", { name: "Chép mã môn COMP2031" });
    expect(copyBtn1).toBeTruthy();
    expect(copyBtn2).toBeTruthy();

    await act(async () => {
      fireEvent.click(copyBtn1);
    });
    expect(writeText).toHaveBeenCalledWith("uuid-comp1013");
    await act(async () => {
      fireEvent.click(copyBtn2);
    });
    expect(writeText).toHaveBeenCalledWith("uuid-comp2031");
  });

  it("đặt hạn mức bằng danh sách chọn lớp, không gõ tay UUID: để trống token nghĩa là không giới hạn (null)", async () => {
    const m = mockApi({
      ...admin,
      "GET /admin/ai-config": err(501, "NOT_IMPLEMENTED"),
      "GET /admin/usage-stats": ok([]),
      "GET /admin/classes-lite": ok([{ id: "cls-1", name: "CTDL&GT – N01" }]),
      "GET /admin/users": ok([]),
      "GET /admin/quotas": ok([]),
      "PUT /admin/quotas": ({ body }) => ok(body),
    });
    open("/admin/quotas");
    await screen.findByText("CTDL&GT – N01"); // chờ danh sách lớp tải xong mới có option để chọn
    fireEvent.change(screen.getByLabelText("Lớp"), { target: { value: "cls-1" } });
    fireEvent.change(screen.getByLabelText(/Giới hạn token/), { target: { value: "500000" } });
    fireEvent.click(screen.getByRole("button", { name: /Lưu hạn mức/ }));
    await waitFor(() => expect(m.called("PUT /admin/quotas")).toHaveLength(1));
    expect(m.called("PUT /admin/quotas")[0].body).toEqual({ scope: "CLASS", scopeId: "cls-1", tokenLimit: 500000, audioMinutesLimit: null });
  });

  it("xử lý cờ vi phạm", async () => {
    const flag = { id: "f1", sessionId: "s", classId: "c", studentId: "u", studentName: "Trần Bảo Châu", type: "PASTE_SUSPECTED", severity: "MEDIUM", detail: "180 ký tự", resolved: false, createdAt: "2026-10-13T07:00:00Z" };
    const m = mockApi({ ...admin, "GET /admin/flags": ok([flag]), "GET /admin/audit-logs": ok([]), "POST /admin/flags/f1/resolve": ok({ ...flag, resolved: true }) });
    open("/admin/flags");
    expect(await screen.findByText("Dán văn bản dài bất thường")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Đánh dấu đã xử lý/ }));
    await waitFor(() => expect(m.called("POST /admin/flags/f1/resolve")).toHaveLength(1));
  });
});

describe("AD-03 Cấu hình AI (GD-15)", () => {
  it("QTV nạp và đổi được model dự phòng từ giao diện", async () => {
    const currentCfg = {
      llm: { kind: "LLM", provider: "gemini", model: "gemini-2.5-flash", fallbackProvider: null, fallbackModel: null, params: {}, quota: {} },
      stt: { kind: "STT", provider: "fake", model: "default", params: {}, quota: {} },
      tts: { kind: "TTS", provider: "fake", model: "default", params: {}, quota: {} },
      audioRetentionDays: 30,
    };
    const m = mockApi({
      ...admin,
      "GET /admin/ai-config": ok(currentCfg),
      "PUT /admin/ai-config": ({ body }) => ok(body),
    });
    open("/admin/ai-config");
    const llm = (await screen.findByRole("region", { name: /Mô hình ngôn ngữ/ })) as HTMLElement;
    fireEvent.change(within(llm).getByLabelText("Model", { selector: "input" }), { target: { value: "gemini-main" } });
    fireEvent.change(within(llm).getByLabelText("Nhà cung cấp dự phòng"), { target: { value: "openai_compat" } });
    fireEvent.change(within(llm).getByLabelText("Model dự phòng"), { target: { value: "gpt-fallback" } });
    fireEvent.click(screen.getByRole("button", { name: /Lưu cấu hình/ }));
    expect(await screen.findByText(/Đã lưu cấu hình AI/)).toBeTruthy();
    expect(m.called("PUT /admin/ai-config")[0].body).toMatchObject({ llm: { model: "gemini-main", fallbackProvider: "openai_compat", fallbackModel: "gpt-fallback" } });
  });
});

describe("Chuông thông báo (GD-15)", () => {
  it("tải lỗi khác danh sách rỗng và có thể thử lại", async () => {
    let failed = true;
    mockApi({ ...admin, "GET /admin/users": ok([]), "GET /notifications": () => failed ? err(500, "INTERNAL_ERROR") : ok([]) });
    open("/admin/users");
    fireEvent.click(await screen.findByRole("button", { name: "Thông báo" }));
    const dialog = within(screen.getByRole("dialog", { name: "Thông báo" }));
    expect(await dialog.findByRole("alert")).toBeTruthy();
    expect(dialog.queryByText("Chưa có thông báo nào.")).toBeNull();
    failed = false;
    fireEvent.click(dialog.getByRole("button", { name: "Thử lại" }));
    expect(await dialog.findByText("Chưa có thông báo nào.")).toBeTruthy();
  });

  it.each([false, true])("đánh dấu đọc lỗi giữ số chưa đọc (tất cả=%s), thử lại thành công", async (all) => {
    const n = { id: "n1", title: "Thông báo thử", isRead: false, createdAt: "", type: "MATCH_PROPOSED" };
    let failed = true;
    mockApi({ ...admin, "GET /admin/users": ok([]), "GET /notifications": ok([n]),
      [all ? "POST /notifications/read-all" : "POST /notifications/n1/read"]: () => failed ? err(500, "INTERNAL_ERROR") : ok({ ...n, isRead: true }),
    });
    open("/admin/users");
    fireEvent.click(await screen.findByRole("button", { name: "Thông báo, 1 chưa đọc" }));
    fireEvent.click(screen.getByRole("button", { name: all ? "Đọc hết" : /Thông báo thử/ }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Thông báo, 1 chưa đọc" })).toBeTruthy();
    failed = false;
    fireEvent.click(screen.getByRole("button", { name: all ? "Đọc hết" : /Thông báo thử/ }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Thông báo, 1 chưa đọc" })).toBeNull());
  });

  it("hiện số chưa đọc, nhận thông báo mới qua WebSocket và đánh dấu đã đọc", async () => {
    const n1 = { id: "n1", type: "MATCH_PROPOSED", title: "Có gợi ý ghép cặp", content: "An muốn học cùng", link: "/sv/classes/c1/peers", isRead: false, createdAt: "" };
    const m = mockApi({ ...admin, "GET /admin/users": ok([]), "GET /notifications": ok([n1]), "POST /notifications/n1/read": ok({ ...n1, isRead: true }) });
    open("/admin/users");
    const bell = await screen.findByRole("button", { name: "Thông báo, 1 chưa đọc" });
    act(() => push({ channel: "user:ad", event: "notification", payload: { ...n1, id: "n2", title: "Thông báo mới", isRead: false } }));
    expect(screen.getByRole("button", { name: "Thông báo, 2 chưa đọc" })).toBeTruthy();
    fireEvent.click(bell);
    fireEvent.click(screen.getByText("Có gợi ý ghép cặp"));
    await waitFor(() => expect(m.called("POST /notifications/n1/read")).toHaveLength(1));
  });
});
