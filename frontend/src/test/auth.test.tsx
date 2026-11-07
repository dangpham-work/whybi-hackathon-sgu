import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { getToken, setToken } from "../lib/api";
import { auth, homeFor, safeNext } from "../lib/auth";
import { routes } from "../router";
import { err, mockApi, ok } from "./mock-api";

const STUDENT = { id: "u-sv", fullName: "Trần Bảo Châu", email: "sv02@whybi.test", role: "STUDENT" };
const LECTURER = { id: "u-gv", fullName: "TS. Nguyễn Văn Bình", email: "gv@whybi.test", role: "LECTURER" };
const TOKENS = { accessToken: "acc-1", refreshToken: "ref-1", tokenType: "bearer", expiresIn: 1800 };

function open(url: string) {
  const router = createMemoryRouter(routes, { initialEntries: [url] });
  render(<RouterProvider router={router} />);
  return router;
}

const fillLogin = async (email: string, password: string) => {
  fireEvent.change(await screen.findByLabelText("Email"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
};

beforeEach(() => auth.reset());
afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

describe("AUTH-01 Đăng nhập (GD-04)", () => {
  it("SV đăng nhập: gửi email + mật khẩu, lưu token, lấy /me rồi vào SV-01", async () => {
    const api = mockApi({ "POST /auth/login": ok(TOKENS), "GET /me": ok(STUDENT), "GET /classes": ok([]) });
    const router = open("/login");
    await fillLogin("sv02@whybi.test", "Whybi@2026");
    await waitFor(() => expect(router.state.location.pathname).toBe("/sv/classes"));
    expect(api.called("POST /auth/login")[0].body).toEqual({ email: "sv02@whybi.test", password: "Whybi@2026" });
    expect(new Headers(api.called("GET /me")[0].init.headers).get("Authorization")).toBe("Bearer acc-1");
    expect(getToken()).toBe("acc-1");
    expect(auth.user?.fullName).toBe("Trần Bảo Châu");
  });

  it("GV đăng nhập thì vào GV-01, QTV vào trang quản trị", async () => {
    mockApi({ "POST /auth/login": ok(TOKENS), "GET /me": ok(LECTURER) });
    const router = open("/login");
    await fillLogin("gv@whybi.test", "Whybi@2026");
    await waitFor(() => expect(router.state.location.pathname).toBe("/gv/classes"));
    expect(homeFor("ADMIN")).toBe("/admin/users");
  });

  it("sai mật khẩu (401) hiện câu dễ hiểu, không phải 'phiên hết hạn'", async () => {
    mockApi({ "POST /auth/login": err(401, "INVALID_CREDENTIALS") });
    open("/login");
    await fillLogin("sv02@whybi.test", "sai");
    expect((await screen.findByRole("alert")).textContent).toContain("Email hoặc mật khẩu không đúng.");
    expect(getToken()).toBeNull();
  });

  it("backend chưa có C2-07 (501) thì báo đang phát triển", async () => {
    mockApi({ "POST /auth/login": err(501, "NOT_IMPLEMENTED", "x", { card: "C2-07" }) });
    open("/login");
    await fillLogin("sv02@whybi.test", "Whybi@2026");
    expect(await screen.findByText("Chức năng đang được phát triển (thẻ C2-07).")).toBeTruthy();
  });

  it("email sai định dạng thì không gửi, hiện nhắc", async () => {
    const api = mockApi({});
    open("/login");
    await fillLogin("khong-phai-email", "x");
    expect(await screen.findByText("Nhập email hợp lệ, ví dụ ten@truong.edu.vn.")).toBeTruthy();
    expect(api.calls).toHaveLength(0);
  });

  it("nút hiện / ẩn mật khẩu có nhãn và aria-pressed cho trình đọc màn hình", async () => {
    open("/login");
    const pw = await screen.findByLabelText("Mật khẩu");
    expect(pw.getAttribute("type")).toBe("password");
    const toggle = screen.getByRole("button", { name: "Hiện ký tự đã nhập" });
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(toggle);
    expect(pw.getAttribute("type")).toBe("text");
    expect(toggle.getAttribute("aria-pressed")).toBe("true");
  });

  it("chỉ một phần tử có nhãn chứa 'Mật khẩu' (e2e SMOKE-04 dùng getByLabel không exact)", async () => {
    open("/login");
    await screen.findByLabelText("Mật khẩu");
    expect(screen.getAllByLabelText(/mật khẩu/i)).toHaveLength(1);
    expect(screen.getAllByLabelText(/email/i)).toHaveLength(1);
  });
});

describe("?next= chỉ nhận đường dẫn nội bộ (chặn open redirect)", () => {
  it.each([
    ["/me", "/me"],
    ["/sv/classes/abc?x=1", "/sv/classes/abc?x=1"],
    ["//evil.com", null],
    ["/\\evil.com", null],
    ["https://evil.com", null],
    ["javascript:alert(1)", null],
    [null, null],
  ])("safeNext(%s) → %s", (input, out) => {
    expect(safeNext(input)).toBe(out);
  });

  it("đăng nhập với ?next=//evil.com thì vẫn về trang theo vai", async () => {
    mockApi({ "POST /auth/login": ok(TOKENS), "GET /me": ok(STUDENT), "GET /classes": ok([]) });
    const router = open("/login?next=%2F%2Fevil.com");
    await fillLogin("sv02@whybi.test", "Whybi@2026");
    await waitFor(() => expect(router.state.location.pathname).toBe("/sv/classes"));
  });

  it("không lưu refresh token vào localStorage (chờ C2-07 chốt cookie httpOnly)", async () => {
    mockApi({ "POST /auth/login": ok(TOKENS), "GET /me": ok(STUDENT), "GET /classes": ok([]) });
    open("/login");
    await fillLogin("sv02@whybi.test", "Whybi@2026");
    await waitFor(() => expect(auth.user).not.toBeNull());
    expect(Object.values({ ...localStorage })).not.toContain("ref-1");
  });
});

describe("AUTH-02 Quên mật khẩu (GD-04)", () => {
  it("gửi email qua JSON và hiện xác nhận trung tính (không lộ email có tồn tại hay không)", async () => {
    const api = mockApi({ "POST /auth/forgot-password": ok(undefined, 202) });
    open("/forgot-password");
    fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "sv02@whybi.test" } });
    fireEvent.click(screen.getByRole("button", { name: "Gửi liên kết đặt lại" }));
    expect(await screen.findByText(/Nếu sv02@whybi.test có tài khoản/)).toBeTruthy();
    expect(api.called("POST /auth/forgot-password")[0].url).toBe("/api/v1/auth/forgot-password");
    expect(api.called("POST /auth/forgot-password")[0].body).toEqual({ email: "sv02@whybi.test" });
  });
});

function deferredResponse() {
  let resolve!: (value: Response) => void;
  const promise = new Promise<Response>((done) => { resolve = done; });
  return { promise, resolve };
}

describe("Phiên đăng nhập không bị request cũ ghi đè", () => {
  it("/me trả muộn sau đăng xuất không khôi phục hồ sơ", async () => {
    const delayed = deferredResponse();
    vi.stubGlobal("fetch", vi.fn((url: string) => url.endsWith("/me") ? delayed.promise : Promise.resolve(ok(undefined, 204))));
    setToken("old-access");
    const pending = auth.ensureUser();
    await auth.logout();
    delayed.resolve(ok(STUDENT));
    await pending;
    expect(auth.user).toBeNull();
    expect(getToken()).toBeNull();
  });

  it("/me của tài khoản cũ không ghi đè tài khoản mới", async () => {
    const delayed = deferredResponse();
    setToken("old-access");
    vi.stubGlobal("fetch", vi.fn((url: string, init: RequestInit) => {
      if (url.endsWith("/auth/login")) return Promise.resolve(ok(TOKENS));
      if (url.endsWith("/me")) return new Headers(init.headers).get("Authorization") === "Bearer old-access" ? delayed.promise : Promise.resolve(ok(LECTURER));
      return Promise.resolve(ok(undefined, 204));
    }));
    const pending = auth.ensureUser();
    await auth.logout();
    await auth.login("gv@whybi.test", "Whybi@2026");
    delayed.resolve(ok(STUDENT));
    await pending;
    expect(auth.user?.id).toBe(LECTURER.id);
  });

  it("đăng nhập trả muộn sau đăng xuất không tạo lại phiên", async () => {
    const delayed = deferredResponse();
    vi.stubGlobal("fetch", vi.fn((url: string) => url.endsWith("/auth/login") ? delayed.promise : Promise.resolve(ok(STUDENT))));
    const pending = auth.login("sv02@whybi.test", "Whybi@2026").catch(() => null);
    await auth.logout();
    delayed.resolve(ok(TOKENS));
    await pending;
    expect(auth.user).toBeNull();
    expect(getToken()).toBeNull();
  });

  it("đăng xuất gửi refresh token và response muộn không xóa phiên mới", async () => {
    const api = mockApi({ "POST /auth/login": ok(TOKENS), "GET /me": ok(STUDENT) });
    await auth.login("sv02@whybi.test", "Whybi@2026");
    const delayed = deferredResponse();
    let logoutBody: unknown;
    vi.stubGlobal("fetch", vi.fn((url: string, init: RequestInit) => {
      if (url.endsWith("/auth/logout")) {
        logoutBody = JSON.parse(String(init.body));
        return delayed.promise;
      }
      return Promise.resolve(url.endsWith("/auth/login") ? ok(TOKENS) : ok(LECTURER));
    }));
    const pending = auth.logout();
    expect(logoutBody).toEqual({ refreshToken: "ref-1" });
    await auth.login("gv@whybi.test", "Whybi@2026");
    delayed.resolve(ok(undefined, 204));
    await pending;
    expect(auth.user?.id).toBe(LECTURER.id);
    expect(api.called("POST /auth/login")).toHaveLength(1);
  });
});

describe("ME-01 Hồ sơ cá nhân (GD-04)", () => {
  it("hiện tên, email, vai trò; đăng xuất thì xóa token và về trang đăng nhập", async () => {
    setToken("acc-1");
    const api = mockApi({ "GET /me": ok(STUDENT), "POST /auth/logout": ok(undefined, 204) });
    const router = open("/me");
    expect(await screen.findByText("Trần Bảo Châu")).toBeTruthy();
    expect(screen.getByText("sv02@whybi.test")).toBeTruthy();
    expect(screen.getByText("Sinh viên")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Đăng xuất" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(api.called("POST /auth/logout")).toHaveLength(1);
    expect(getToken()).toBeNull();
    expect(auth.user).toBeNull();
  });

  it("chưa đăng nhập thì mời đăng nhập", async () => {
    mockApi({});
    open("/me");
    expect(await screen.findByRole("link", { name: "Đăng nhập" })).toBeTruthy();
  });

  it("đăng xuất vẫn xóa phiên khi máy chủ lỗi", async () => {
    setToken("acc-1");
    mockApi({ "GET /me": ok(STUDENT), "POST /auth/logout": err(500, "BOOM") });
    const router = open("/me");
    fireEvent.click(await screen.findByRole("button", { name: "Đăng xuất" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(getToken()).toBeNull();
  });
});
