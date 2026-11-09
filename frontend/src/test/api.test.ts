import { api, apiCall, ApiError, errorText, FRIENDLY, friendlyMessage, getToken, onSessionExpired, setRefreshToken, setToken, type Schema } from "../lib/api";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const fail = (status: number, code: string, message = "server says", details = {}) => json(status, { error: { code, message, details } });

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  setToken(null);
});
afterEach(() => vi.unstubAllGlobals());

const lastCall = () => {
  const [url, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
  return { url, init, headers: new Headers(init.headers) };
};

describe("api() – gọi API cấp thấp (GD-02)", () => {
  it("gắn tiền tố /api/v1, token và Content-Type JSON", async () => {
    setToken("tok-1");
    fetchMock.mockResolvedValue(json(200, { ok: 1 }));
    expect(await api("/me", { method: "PATCH", body: JSON.stringify({ a: 1 }) })).toEqual({ ok: 1 });
    const { url, headers } = lastCall();
    expect(url).toBe("/api/v1/me");
    expect(headers.get("Authorization")).toBe("Bearer tok-1");
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("không ép Content-Type khi gửi FormData (để trình duyệt tự đặt boundary)", async () => {
    fetchMock.mockResolvedValue(json(200, {}));
    await api("/sessions/x/audio", { method: "POST", body: new FormData() });
    expect(lastCall().headers.has("Content-Type")).toBe(false);
  });

  it("204 hoặc thân rỗng trả undefined", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    expect(await api("/auth/logout", { method: "POST" })).toBeUndefined();
    fetchMock.mockResolvedValueOnce(new Response("", { status: 200 }));
    expect(await api("/auth/logout", { method: "POST" })).toBeUndefined();
  });
});

describe("lỗi API hiện thông báo dễ hiểu (Xong khi GD-02)", () => {
  it("mã lỗi đã biết → câu tiếng Việt trong FRIENDLY, giữ code / status / details", async () => {
    fetchMock.mockResolvedValue(fail(409, "CYCLE_DETECTED", "cycle", { path: ["a", "b", "a"] }));
    const e = await api("/x").catch((err: unknown) => err);
    expect(e).toBeInstanceOf(ApiError);
    expect(e).toMatchObject({ status: 409, code: "CYCLE_DETECTED", details: { path: ["a", "b", "a"] }, serverMessage: "cycle" });
    expect((e as ApiError).message).toBe("Cạnh này tạo chu trình trong cây kỹ năng.");
  });

  it("501 NOT_IMPLEMENTED → 'đang phát triển' kèm mã thẻ, đánh dấu notImplemented", async () => {
    fetchMock.mockResolvedValue(fail(501, "NOT_IMPLEMENTED", "Chưa cài đặt – xem thẻ C2-07", { card: "C2-07" }));
    const e = (await api("/me").catch((err: unknown) => err)) as ApiError;
    expect(e.notImplemented).toBe(true);
    expect(e.message).toBe("Chức năng đang được phát triển (thẻ C2-07).");
  });

  it("mất mạng → NETWORK_ERROR, không lộ lỗi kỹ thuật", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const e = (await api("/me").catch((err: unknown) => err)) as ApiError;
    expect(e).toMatchObject({ status: 0, code: "NETWORK_ERROR" });
    expect(e.message).toBe("Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.");
  });

  it("thân lỗi không phải JSON (vd. nginx 502) → thông báo theo mã HTTP", async () => {
    fetchMock.mockResolvedValue(new Response("<html>Bad Gateway</html>", { status: 502 }));
    const e = (await api("/me").catch((err: unknown) => err)) as ApiError;
    expect(e).toMatchObject({ status: 502, code: "HTTP_ERROR" });
    expect(e.message).toBe("Máy chủ đang bận hoặc gặp sự cố. Vui lòng thử lại sau ít phút.");
  });

  it("hủy yêu cầu (AbortController) ném lại AbortError, không đổi thành lỗi mạng", async () => {
    fetchMock.mockRejectedValue(new DOMException("aborted", "AbortError"));
    await expect(api("/me")).rejects.toMatchObject({ name: "AbortError" });
  });

  it.each([
    [401, "UNAUTHORIZED", "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại."],
    [403, "FORBIDDEN", "Bạn không có quyền xem nội dung này."],
    [404, "CLASS_NOT_FOUND", "Không tìm thấy lớp học (có thể đã bị xóa hoặc bạn chưa tham gia)."],
    [404, "SOMETHING_NEW", "Không tìm thấy nội dung bạn cần."],
    [422, "VALIDATION_ERROR", "Dữ liệu gửi lên chưa hợp lệ, vui lòng kiểm tra lại."],
    [429, "RATE_LIMITED", "Bạn thao tác quá nhanh, chờ một chút rồi thử lại."],
    [500, "WEIRD", "Máy chủ đang bận hoặc gặp sự cố. Vui lòng thử lại sau ít phút."],
    [418, "TEAPOT", "Có lỗi xảy ra, vui lòng thử lại."],
  ])("friendlyMessage(%i, %s)", (status, code, text) => {
    expect(friendlyMessage(status, code)).toBe(text);
  });
});

// #154: mã lỗi của POST /sessions/{id}/audio (backend/app/services/speech.py, session_history.py) – Bảng 7.4 đề cương
describe("lỗi ghi âm / STT có thông báo riêng, gợi ý gõ chữ (#154)", () => {
  it.each([
    [503, "STT_UNAVAILABLE"],
    [422, "NO_SPEECH_DETECTED"],
    [422, "EMPTY_AUDIO"],
    [415, "UNSUPPORTED_AUDIO_FORMAT"],
    [413, "AUDIO_TOO_LONG"],
    [413, "AUDIO_TOO_LARGE"],
    [503, "AUDIO_STORE_UNAVAILABLE"],
  ])("%i %s → câu riêng có gợi ý gõ chữ", (status, code) => {
    const text = friendlyMessage(status, code);
    expect(text).toMatch(/gõ chữ/);
    expect(text).not.toMatch(/Máy chủ đang bận|chưa hợp lệ/);
  });

  it("NO_SPEECH_DETECTED dùng đúng câu 'chưa nghe rõ' của SV-04", () => {
    expect(friendlyMessage(422, "NO_SPEECH_DETECTED")).toBe("Whybi chưa nghe rõ lời bạn. Hãy ghi lại gần micro hơn, hoặc gõ chữ.");
  });

  it("LLM_UNAVAILABLE có câu riêng, không rơi về câu chung theo 503", () => {
    expect(friendlyMessage(503, "LLM_UNAVAILABLE")).toBe(FRIENDLY.LLM_UNAVAILABLE);
    expect(FRIENDLY.LLM_UNAVAILABLE).toMatch(/Whybi/);
  });

  it("NO_SOURCE_MATERIAL có câu riêng nhắc tải giáo trình (#190)", () => {
    expect(friendlyMessage(422, "NO_SOURCE_MATERIAL")).toBe(FRIENDLY.NO_SOURCE_MATERIAL);
    expect(FRIENDLY.NO_SOURCE_MATERIAL).toMatch(/Lớp chưa có giáo trình.*hãy tải giáo trình lên trước/);
  });

  it("errorText() của ApiError STT trả câu gợi ý gõ chữ", () => {
    expect(errorText(new ApiError(503, "STT_UNAVAILABLE", "Dịch vụ nhận dạng giọng nói lỗi"))).toMatch(/gõ chữ/);
  });
});

// Access token hết hạn sau 30 phút (NFR-07): trước đây không tự làm mới / đăng xuất nên trang "treo" ở lỗi 401.
describe("api() tự làm mới access token hết hạn rồi thử lại (C2-24)", () => {
  afterEach(() => setRefreshToken(null));

  it("401 ở yêu cầu thường ⇒ làm mới rồi thử lại, thành công thì không ném lỗi", async () => {
    setToken("acc-cu");
    setRefreshToken("ref-1");
    fetchMock
      .mockResolvedValueOnce(fail(401, "TOKEN_EXPIRED"))
      .mockResolvedValueOnce(json(200, { accessToken: "acc-moi", refreshToken: "ref-2", tokenType: "bearer", expiresIn: 1800 }))
      .mockResolvedValueOnce(json(200, { fullName: "A" }));
    const me = await apiCall("get", "/me");
    expect(me).toEqual({ fullName: "A" });
    expect(getToken()).toBe("acc-moi");
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(new Headers(fetchMock.mock.calls[2]![1].headers).get("Authorization")).toBe("Bearer acc-moi");
  });

  it("làm mới cũng thất bại (hoặc không có refresh token) ⇒ gọi onSessionExpired đúng một lần, vẫn ném lỗi 401 gốc", async () => {
    setToken("acc-cu");
    setRefreshToken("ref-het-han");
    fetchMock.mockResolvedValueOnce(fail(401, "TOKEN_EXPIRED")).mockResolvedValueOnce(fail(401, "TOKEN_REVOKED"));
    const onExpired = vi.fn();
    onSessionExpired(onExpired);
    await expect(apiCall("get", "/me")).rejects.toMatchObject({ status: 401, code: "TOKEN_EXPIRED" });
    expect(onExpired).toHaveBeenCalledTimes(1);
  });

  it("401 ở chính /auth/login không tự làm mới / không gọi onSessionExpired (đó là sai mật khẩu, không phải hết hạn)", async () => {
    setRefreshToken("ref-1");
    fetchMock.mockResolvedValue(fail(401, "INVALID_CREDENTIALS"));
    const onExpired = vi.fn();
    onSessionExpired(onExpired);
    await expect(apiCall("post", "/auth/login", { body: { email: "a@x.vn", password: "x" } })).rejects.toMatchObject({ code: "INVALID_CREDENTIALS" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(onExpired).not.toHaveBeenCalled();
  });
});

describe("apiCall() – gọi API có kiểu từ OpenAPI", () => {
  it("điền tham số đường dẫn và query", async () => {
    fetchMock.mockResolvedValue(json(200, { nodes: [], edges: [] }));
    const tree = await apiCall("get", "/classes/{class_id}/tree", { path: { class_id: "c 1" }, query: { draft: true } });
    expect(lastCall().url).toBe("/api/v1/classes/c%201/tree?draft=true");
    expectTypeOf(tree).toEqualTypeOf<Schema<"TreeVersion">>();
  });

  it("gửi body JSON đúng schema và trả kiểu phản hồi", async () => {
    fetchMock.mockResolvedValue(json(200, { sessionId: "s1" }));
    const created = await apiCall("post", "/sessions", { body: { nodeId: "n1", inputMode: "TEXT", ttsEnabled: false } });
    const { init } = lastCall();
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ nodeId: "n1", inputMode: "TEXT", ttsEnabled: false });
    expectTypeOf(created).toEqualTypeOf<Schema<"SessionCreated">>();
  });

  it("endpoint không cần tham số thì bỏ trống được", async () => {
    fetchMock.mockResolvedValue(json(200, { id: "u" }));
    const me = await apiCall("get", "/me");
    expectTypeOf(me).toEqualTypeOf<Schema<"Me">>();
  });

  it("upload multipart nhận FormData; 204 trả void", async () => {
    fetchMock.mockResolvedValueOnce(json(200, { text: "xin chào" }));
    const form = new FormData();
    const t = await apiCall("post", "/sessions/{session_id}/audio", { path: { session_id: "s1" }, body: form });
    expect(lastCall().init.body).toBe(form);
    expectTypeOf(t).toEqualTypeOf<Schema<"Transcript">>();

    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    const r = await apiCall("delete", "/edges/{edge_id}", { path: { edge_id: "e1" } });
    expect(lastCall().init.method).toBe("DELETE");
    expectTypeOf(r).toEqualTypeOf<void>();
  });

  it("sai đường dẫn / thiếu tham số / sai body bị tsc chặn", () => {
    // Chỉ kiểm kiểu – không chạy.
    const typeOnly = () => {
      // @ts-expect-error đường dẫn không có trong OpenAPI
      void apiCall("get", "/khong-co");
      // @ts-expect-error thiếu path.class_id
      void apiCall("get", "/classes/{class_id}/tree");
      // @ts-expect-error inputMode sai giá trị enum
      void apiCall("post", "/sessions", { body: { nodeId: "n1", inputMode: "FAX", ttsEnabled: false } });
      // @ts-expect-error /sessions không có GET
      void apiCall("get", "/sessions");
    };
    expect(typeof typeOnly).toBe("function");
  });
});
