import { ApiError, FRIENDLY, UNAUTHORIZED_EVENT, api, errorMessage, getToken, http, isAbort, setToken } from "../lib/api";

function jsonResponse(status: number, body: unknown) {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("lớp gọi API (GD-02)", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    setToken(null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("gọi đúng /api/v1, gắn token và gửi JSON", async () => {
    setToken("abc");
    fetchMock.mockResolvedValue(jsonResponse(201, { id: "c1" }));
    const out = await http.post<{ id: string }>("/classes", { name: "CTDL" });
    expect(out).toEqual({ id: "c1" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/classes");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ name: "CTDL" }));
    const headers = init.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer abc");
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("FormData gửi nguyên, không đặt Content-Type", async () => {
    fetchMock.mockResolvedValue(jsonResponse(202, { jobId: "j1" }));
    const fd = new FormData();
    fd.append("file", new Blob(["x"]), "a.pdf");
    await http.post("/classes/1/syllabi", fd);
    const init = fetchMock.mock.calls[0][1];
    expect(init.body).toBe(fd);
    expect((init.headers as Headers).has("Content-Type")).toBe(false);
  });

  it("204 trả undefined", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(http.del("/edges/1")).resolves.toBeUndefined();
  });

  it("lỗi có mã nghiệp vụ hiện thông báo dễ hiểu và giữ details", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(409, { error: { code: "CYCLE_DETECTED", message: "cycle", details: { path: ["a", "b", "a"] } } }),
    );
    const err = (await api("/tree-versions/1/edges", { method: "POST", body: {} }).catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(409);
    expect(err.code).toBe("CYCLE_DETECTED");
    expect(err.message).toBe(FRIENDLY.CYCLE_DETECTED);
    expect(err.details).toEqual({ path: ["a", "b", "a"] });
  });

  it("mã lạ thì dùng message của backend", async () => {
    fetchMock.mockResolvedValue(jsonResponse(400, { error: { code: "CLASS_FULL", message: "Lớp đã đủ 60 SV" } }));
    await expect(http.get("/x")).rejects.toMatchObject({ code: "CLASS_FULL", message: "Lớp đã đủ 60 SV" });
  });

  it("không có thân lỗi chuẩn (vd. nginx 502) vẫn có câu dễ hiểu", async () => {
    fetchMock.mockResolvedValue(new Response("<html>Bad Gateway</html>", { status: 502 }));
    await expect(http.get("/x")).rejects.toMatchObject({ status: 502, code: "SERVER_ERROR", message: FRIENDLY.SERVER_ERROR });
  });

  it("401 xóa token và phát sự kiện để về trang đăng nhập", async () => {
    setToken("old");
    const listener = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, listener);
    fetchMock.mockResolvedValue(jsonResponse(401, { error: { code: "UNAUTHORIZED", message: "x" } }));
    await expect(http.get("/auth/me")).rejects.toMatchObject({ message: FRIENDLY.UNAUTHORIZED });
    expect(getToken()).toBeNull();
    expect(listener).toHaveBeenCalledOnce();
    window.removeEventListener(UNAUTHORIZED_EVENT, listener);
  });

  it("mất mạng thành NETWORK_ERROR", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(http.get("/x")).rejects.toMatchObject({ status: 0, code: "NETWORK_ERROR", message: FRIENDLY.NETWORK_ERROR });
  });

  it("quá thời gian chờ thành TIMEOUT", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise((_res, rej) => init.signal!.addEventListener("abort", () => rej(new DOMException("aborted", "AbortError")))),
    );
    const p = http.get("/slow", { timeoutMs: 1000 }).catch((e) => e);
    await vi.advanceTimersByTimeAsync(1000);
    expect(await p).toMatchObject({ code: "TIMEOUT", message: FRIENDLY.TIMEOUT });
  });

  it("bên gọi tự hủy thì ném lại AbortError (không hiện lỗi)", async () => {
    fetchMock.mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise((_res, rej) => init.signal!.addEventListener("abort", () => rej(new DOMException("aborted", "AbortError")))),
    );
    const ctrl = new AbortController();
    const p = http.get("/x", { signal: ctrl.signal }).catch((e) => e);
    ctrl.abort();
    expect(isAbort(await p)).toBe(true);
  });

  it("errorMessage luôn trả câu dễ hiểu", () => {
    expect(errorMessage(new ApiError(403, "FORBIDDEN", FRIENDLY.FORBIDDEN))).toBe(FRIENDLY.FORBIDDEN);
    expect(errorMessage(new Error("TypeError: x is undefined"))).toBe(FRIENDLY.HTTP_ERROR);
    expect(errorMessage("lạ")).toBe(FRIENDLY.HTTP_ERROR);
  });
});
