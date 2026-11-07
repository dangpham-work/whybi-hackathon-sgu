import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { setToken } from "../lib/api";
import { auth } from "../lib/auth";
import { routes } from "../router";
import { err, mockApi, ok } from "./mock-api";

const SID = "5e0c7a52-2f4b-4c55-9a43-0d1d3d2c9b11";
const OPENING = { text: "Mình chưa hiểu con trỏ là gì, bạn giảng giúp mình nhé?", strategy: null };
const Q2 = { text: "Nếu hai con trỏ cùng trỏ vào một ô nhớ thì sao?", strategy: "EDGE_CASE" };
const REPLY = { status: "CHALLENGING", question: Q2, questionsAsked: 1, questionsTotal: 4 };
const TRANSCRIPT = {
  text: "Con trỏ là biến lưu địa chỉ của một ô nhớ khác",
  confidence: 0.93,
  words: [],
  lowConfidenceWords: [],
  audioRef: "audio/s1/turn-1.webm",
  needsConfirmation: false,
};

// ---------------------------------------------------------------- giả lập micro + MediaRecorder

class FakeRecorder {
  static instances: FakeRecorder[] = [];
  static isTypeSupported = () => true;
  state: "inactive" | "recording" = "inactive";
  mimeType = "audio/webm";
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  start = vi.fn(() => {
    this.state = "recording";
  });
  stop = vi.fn(() => {
    if (this.state === "inactive") return;
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["âm-thanh"], { type: "audio/webm" }) });
    this.onstop?.();
  });
  constructor(public stream: MediaStream) {
    FakeRecorder.instances.push(this);
  }
}

/** WebSocket giả: không mở mạng thật; test bơm tin bằng onmessage. */
class FakeWS {
  static instances: FakeWS[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  send = vi.fn();
  close = vi.fn();
  constructor() {
    FakeWS.instances.push(this);
  }
}

function stubMic(getUserMedia = vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] }) as unknown as MediaStream)) {
  FakeRecorder.instances = [];
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia } });
  return getUserMedia;
}

function open(state: unknown = { opening: OPENING, nodeTitle: "N5 – Con trỏ" }) {
  const router = createMemoryRouter(routes, { initialEntries: [{ pathname: `/sv/sessions/${SID}`, state }] });
  render(<RouterProvider router={router} />);
  return router;
}

const turnsKey = `POST /sessions/${SID}/turns`;
const audioKey = `POST /sessions/${SID}/audio`;

const getKey = `GET /sessions/${SID}`;
const NOW = "2026-10-26T08:00:00Z";
/** GET /sessions/{id} của phiên vừa mở: chỉ có câu mở đầu. */
const FRESH = {
  sessionId: SID,
  nodeId: "7d3f1c2a-1111-4c55-9a43-0d1d3d2c9b11",
  status: "EXPLAINING",
  inputMode: "TEXT",
  ttsEnabled: false,
  turns: [{ turnNo: 1, speaker: "TUTEE", turnType: "OPENING", text: OPENING.text, inputMode: "TEXT", createdAt: NOW }],
  question: OPENING,
  questionsAsked: 0,
  questionsTotal: 4,
  startedAt: NOW,
};
/** Phiên chưa có câu hỏi nào (câu mở đầu còn đang tới qua WebSocket). */
const EMPTY = { ...FRESH, status: "CREATED", turns: [], question: null, questionsTotal: 0 };

/** Giả lập backend, mặc định GET /sessions/{id} trả phiên vừa mở. */
const backend = (routes: Parameters<typeof mockApi>[0], state: unknown = FRESH) => mockApi({ [getKey]: ok(state), ...routes });

beforeEach(() => {
  vi.stubGlobal("WebSocket", FakeWS);
  auth.reset();
  setToken("acc-1");
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  setToken(null);
});

describe("SV-04 Phiên giảng lại (GD-07)", () => {
  it("hiện câu mở đầu của Whybi và tên nút", async () => {
    backend({});
    open();
    expect(await screen.findByText(OPENING.text)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "N5 – Con trỏ" })).toBeTruthy();
    expect(screen.getByText(/Whybi sẽ không đưa đáp án/)).toBeTruthy();
  });

  it("chưa có câu mở đầu (tải lại trang) thì báo đang chờ Whybi", async () => {
    backend({}, EMPTY);
    open(null);
    expect(await screen.findByText(/Whybi đang chuẩn bị câu hỏi/)).toBeTruthy();
  });

  it("chờ câu mở đầu quá lâu thì mở khóa ô trả lời để SV giảng tiếp, không chờ vô hạn", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    backend({}, EMPTY);
    stubMic();
    open(null);
    expect(await screen.findByText(/Whybi đang chuẩn bị câu hỏi/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Bắt đầu ghi âm" }) as HTMLButtonElement).disabled).toBe(true);
    // đồng hồ chờ chỉ chạy sau khi GET /sessions/{id} xong ⇒ tiến giờ bất đồng bộ để effect kịp đặt hẹn giờ
    await act(async () => {
      await vi.advanceTimersByTimeAsync(8_000);
    });
    expect(screen.queryByText(/Whybi đang chuẩn bị câu hỏi/)).toBeNull();
    expect(screen.getByText(/Bạn cứ giảng tiếp/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Bắt đầu ghi âm" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("câu hỏi tới qua kênh session:{id} thì hiện trong hội thoại", async () => {
    backend({}, EMPTY);
    open(null);
    await screen.findByText(/Whybi đang chuẩn bị câu hỏi/);
    // Trang lazy có thể đã hiện chữ trước khi effect tạo socket và gắn handler.
    await waitFor(() => expect(FakeWS.instances.at(-1)?.onmessage).toBeTypeOf("function"));
    act(() => {
      FakeWS.instances.at(-1)!.onmessage!({ data: JSON.stringify({ channel: `session:${SID}`, event: "session.question", payload: OPENING }) });
    });
    expect(await screen.findByText(OPENING.text)).toBeTruthy();
    expect(screen.queryByText(/Whybi đang chuẩn bị câu hỏi/)).toBeNull();
  });

  it("gửi một lượt bằng chữ kèm pasteRatio, typingCps, responseTimeMs; câu hỏi tiếp theo hiện ra", async () => {
    const api = backend({ [turnsKey]: ok(REPLY) });
    open();
    fireEvent.click(await screen.findByRole("tab", { name: /Văn bản/ }));
    const box = screen.getByRole("textbox", { name: /Lời giảng của bạn/ });
    const pasted = "Con trỏ là biến lưu địa chỉ";
    fireEvent.paste(box, { clipboardData: { getData: () => pasted } });
    fireEvent.change(box, { target: { value: pasted } });
    fireEvent.change(box, { target: { value: pasted + " ô nhớ" } });
    fireEvent.click(screen.getByRole("button", { name: "Gửi lời giảng" }));

    expect(await screen.findByText(Q2.text)).toBeTruthy();
    const [call] = api.called(turnsKey);
    const body = call.body as Record<string, unknown>;
    expect(body).toMatchObject({ turnType: "EXPLANATION", inputMode: "TEXT", text: pasted + " ô nhớ" });
    expect(body.pasteRatio).toBeGreaterThan(0.5);
    expect(body.pasteRatio).toBeLessThan(1);
    expect(typeof body.typingCps).toBe("number");
    expect(typeof body.responseTimeMs).toBe("number");
    expect(body.audioRef).toBeUndefined();
    // lời giảng đã gửi hiện trong hội thoại, ô gõ trống lại, tiến độ phản biện cập nhật
    expect(screen.getByText(pasted + " ô nhớ")).toBeTruthy();
    expect((screen.getByRole("textbox", { name: /Câu trả lời của bạn/ }) as HTMLTextAreaElement).value).toBe("");
    expect(screen.getByText("Câu phản biện 1/4")).toBeTruthy();
  });

  it("câu hỏi tới qua WebSocket trước khi HTTP trả lời thì không hiện trùng, vẫn nằm sau lời giảng", async () => {
    backend({
      [turnsKey]: () => {
        FakeWS.instances.at(-1)!.onmessage!({ data: JSON.stringify({ channel: `session:${SID}`, event: "session.question", payload: Q2 }) });
        return ok(REPLY);
      },
    });
    open();
    fireEvent.click(await screen.findByRole("tab", { name: /Văn bản/ }));
    fireEvent.change(screen.getByRole("textbox", { name: /Lời giảng/ }), { target: { value: "lời giảng của mình" } });
    await waitFor(() => expect(FakeWS.instances.at(-1)?.onmessage).toBeTypeOf("function"));
    fireEvent.click(screen.getByRole("button", { name: "Gửi lời giảng" }));
    await screen.findByText("Câu phản biện 1/4");
    expect(screen.getAllByText(Q2.text)).toHaveLength(1);
    const log = screen.getByRole("log", { name: "Hội thoại với Whybi" }).textContent ?? "";
    expect(log.indexOf("lời giảng của mình")).toBeLessThan(log.indexOf(Q2.text));
  });

  it("lượt sau câu phản biện gửi turnType ANSWER", async () => {
    const api = backend({ [turnsKey]: ok(REPLY) });
    open();
    fireEvent.click(await screen.findByRole("tab", { name: /Văn bản/ }));
    fireEvent.change(screen.getByRole("textbox", { name: /Lời giảng/ }), { target: { value: "giảng" } });
    fireEvent.click(screen.getByRole("button", { name: "Gửi lời giảng" }));
    await screen.findByText(Q2.text);
    fireEvent.change(screen.getByRole("textbox", { name: /Câu trả lời/ }), { target: { value: "trả lời" } });
    fireEvent.click(screen.getByRole("button", { name: "Gửi câu trả lời" }));
    await waitFor(() => expect(api.called(turnsKey)).toHaveLength(2));
    expect(api.called(turnsKey)[1].body).toMatchObject({ turnType: "ANSWER", text: "trả lời" });
  });

  it("phiên đã kết thúc (409) thì báo lỗi dễ hiểu, giữ nguyên chữ đã gõ", async () => {
    backend({ [turnsKey]: err(409, "SESSION_NOT_ACTIVE", "Phiên đã kết thúc") });
    open();
    fireEvent.click(await screen.findByRole("tab", { name: /Văn bản/ }));
    const box = screen.getByRole("textbox", { name: /Lời giảng/ });
    fireEvent.change(box, { target: { value: "giảng" } });
    fireEvent.click(screen.getByRole("button", { name: "Gửi lời giảng" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/Phiên này đã kết thúc/);
    expect((box as HTMLTextAreaElement).value).toBe("giảng");
  });

  it("hết câu hỏi thì báo đang chấm và có đường sang kết quả", async () => {
    backend({ [turnsKey]: ok({ status: "COMPLETED", question: null, questionsAsked: 4, questionsTotal: 4 }) });
    open();
    fireEvent.click(await screen.findByRole("tab", { name: /Văn bản/ }));
    fireEvent.change(screen.getByRole("textbox", { name: /Lời giảng/ }), { target: { value: "giảng" } });
    fireEvent.click(screen.getByRole("button", { name: "Gửi lời giảng" }));
    const link = await screen.findByRole("link", { name: /Xem kết quả/ });
    expect(link.getAttribute("href")).toBe(`/sv/sessions/${SID}/result`);
    expect(screen.queryByRole("tab", { name: /Văn bản/ })).toBeNull();
  });

  describe("tải lại trang (bug #153)", () => {
    const EXPLAIN = "Con trỏ là biến lưu địa chỉ ô nhớ";
    const deadline = () => new Date(Date.now() + 75_000).toISOString();
    const midChallenge = () => ({
      ...FRESH,
      status: "CHALLENGING",
      turns: [
        ...FRESH.turns,
        { turnNo: 2, speaker: "STUDENT", turnType: "EXPLANATION", text: EXPLAIN, inputMode: "TEXT", createdAt: NOW },
        { turnNo: 3, speaker: "TUTEE", turnType: "SYSTEM_NOTICE", text: "Câu trả lời trước đã hết giờ.", inputMode: "TEXT", createdAt: NOW },
        { turnNo: 4, speaker: "TUTEE", turnType: "QUESTION", text: Q2.text, inputMode: "TEXT", createdAt: NOW },
      ],
      question: { ...Q2, deadline: deadline() },
      questionsAsked: 2,
      questionsTotal: 4,
    });

    it("mở trang không có location state thì tải GET /sessions/{id}: hội thoại, câu chờ, đồng hồ, tiến độ, giai đoạn ANSWER", async () => {
      const api = backend({ [turnsKey]: ok(REPLY) }, midChallenge());
      open(null);
      expect(await screen.findByText(Q2.text)).toBeTruthy();
      expect(api.called(getKey)).toHaveLength(1);
      expect(screen.getByText(OPENING.text)).toBeTruthy();
      expect(screen.getByText(EXPLAIN)).toBeTruthy();
      expect(screen.getByText("Câu trả lời trước đã hết giờ.")).toBeTruthy();
      expect(screen.getByText("Câu phản biện 2/4")).toBeTruthy();
      expect(screen.getByRole("timer").getAttribute("aria-label")).toMatch(/^Còn (7[0-5]) giây để trả lời$/);
      expect(screen.queryByText(/Whybi đang chuẩn bị câu hỏi/)).toBeNull();
      // đúng giai đoạn: lượt kế là ANSWER, không quay về EXPLAINING
      fireEvent.click(screen.getByRole("tab", { name: /Văn bản/ }));
      fireEvent.change(screen.getByRole("textbox", { name: /Câu trả lời của bạn/ }), { target: { value: "trả lời" } });
      fireEvent.click(screen.getByRole("button", { name: "Gửi câu trả lời" }));
      await waitFor(() => expect(api.called(turnsKey)).toHaveLength(1));
      expect(api.called(turnsKey)[0].body).toMatchObject({ turnType: "ANSWER", text: "trả lời" });
    });

    it("có location state (F5 giữ history.state) vẫn lấy hội thoại đầy đủ từ máy chủ", async () => {
      backend({}, midChallenge());
      open({ opening: OPENING, nodeTitle: "N5 – Con trỏ" });
      expect(await screen.findByText(Q2.text)).toBeTruthy();
      expect(screen.getAllByText(OPENING.text)).toHaveLength(1);
      expect(screen.getByText("Câu phản biện 2/4")).toBeTruthy();
      expect(screen.getByRole("heading", { name: "N5 – Con trỏ" })).toBeTruthy();
    });

    it("câu đang chờ tới lại qua WebSocket sau khi khôi phục thì không hiện trùng", async () => {
      backend({}, midChallenge());
      open(null);
      await screen.findByText(Q2.text);
      await waitFor(() => expect(FakeWS.instances.length).toBeGreaterThan(0));
      act(() => {
        FakeWS.instances.at(-1)!.onmessage!({ data: JSON.stringify({ channel: `session:${SID}`, event: "session.question", payload: Q2 }) });
      });
      expect(screen.getAllByText(Q2.text)).toHaveLength(1);
    });

    it("đang tải phiên thì báo đang tải và khóa ô trả lời", async () => {
      mockApi({ [getKey]: () => new Promise<Response>(() => {}) as unknown as Response });
      stubMic();
      open(null);
      expect(await screen.findByText(/Đang tải lại phiên/)).toBeTruthy();
      expect((screen.getByRole("button", { name: "Bắt đầu ghi âm" }) as HTMLButtonElement).disabled).toBe(true);
    });

    it("tải phiên lỗi thì báo lỗi dễ hiểu, bấm Thử lại thì tải lại được", async () => {
      let fail = true;
      const api = mockApi({ [getKey]: () => (fail ? err(500, "INTERNAL", "lỗi") : ok(midChallenge())) });
      open(null);
      const alert = await screen.findByRole("alert");
      expect(alert.textContent).toMatch(/Chưa tải lại được phiên/);
      fail = false;
      fireEvent.click(within(alert).getByRole("button", { name: /Thử lại/ }));
      expect(await screen.findByText(Q2.text)).toBeTruthy();
      expect(screen.queryByRole("alert")).toBeNull();
      expect(api.called(getKey)).toHaveLength(2);
    });

    it("phiên đã kết thúc thì hiện hội thoại và đường sang kết quả", async () => {
      backend({}, { ...midChallenge(), status: "COMPLETED", question: null, questionsAsked: 4, questionsTotal: 4 });
      open(null);
      expect(await screen.findByRole("link", { name: /Xem kết quả/ })).toBeTruthy();
      expect(screen.getByText(EXPLAIN)).toBeTruthy();
      expect(screen.queryByRole("timer")).toBeNull();
    });
  });

  describe("giọng nói (FR-TB-05, BR-13)", () => {
    it("hỏi đồng ý trước – chưa đồng ý thì không xin micro", async () => {
      backend({});
      const getUserMedia = stubMic();
      open();
      fireEvent.click(await screen.findByRole("button", { name: "Bắt đầu ghi âm" }));
      const dialog = screen.getByRole("dialog", { name: /Cho phép ghi âm/ });
      expect(getUserMedia).not.toHaveBeenCalled();
      fireEvent.click(within(dialog).getByRole("button", { name: "Không, tôi sẽ gõ chữ" }));
      expect(getUserMedia).not.toHaveBeenCalled();
      expect(screen.queryByRole("dialog")).toBeNull();
      // từ chối ghi âm → chuyển sang ô gõ
      expect(screen.getByRole("tab", { name: /Văn bản/ }).getAttribute("aria-selected")).toBe("true");
    });

    it("gửi một lượt bằng giọng nói: tải âm thanh lên rồi gửi lượt VOICE có audioRef", async () => {
      const api = backend({ [audioKey]: ok(TRANSCRIPT), [turnsKey]: ok(REPLY) });
      const getUserMedia = stubMic();
      open();
      fireEvent.click(await screen.findByRole("button", { name: "Bắt đầu ghi âm" }));
      fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Đồng ý ghi âm" }));
      expect(await screen.findByText("Đang ghi")).toBeTruthy();
      expect(getUserMedia).toHaveBeenCalledWith({ audio: true });
      expect(FakeRecorder.instances[0].start).toHaveBeenCalled();

      fireEvent.click(screen.getByRole("button", { name: "Gửi bản ghi" }));
      expect(await screen.findByText(Q2.text)).toBeTruthy();

      const [upload] = api.called(audioKey);
      expect(upload.init.body).toBeInstanceOf(FormData);
      expect((upload.init.body as FormData).get("file")).toBeInstanceOf(Blob);
      // BR-13: SV đã đồng ý ⇒ gửi consent=true để backend (C1-12) lưu ghi âm
      expect((upload.init.body as FormData).get("consent")).toBe("true");
      const body = api.called(turnsKey)[0].body as Record<string, unknown>;
      expect(body).toMatchObject({
        turnType: "EXPLANATION",
        inputMode: "VOICE",
        text: TRANSCRIPT.text,
        audioRef: TRANSCRIPT.audioRef,
        sttConfidence: TRANSCRIPT.confidence,
        transcriptEdited: false,
      });
      expect(screen.getByText(TRANSCRIPT.text)).toBeTruthy();
    });

    it("đã đồng ý một lần thì lượt sau không hỏi lại", async () => {
      backend({ [audioKey]: ok(TRANSCRIPT), [turnsKey]: ok(REPLY) });
      stubMic();
      open();
      fireEvent.click(await screen.findByRole("button", { name: "Bắt đầu ghi âm" }));
      fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Đồng ý ghi âm" }));
      await screen.findByText("Đang ghi");
      fireEvent.click(screen.getByRole("button", { name: "Gửi bản ghi" }));
      await screen.findByText(Q2.text);
      fireEvent.click(await screen.findByRole("button", { name: "Bắt đầu ghi âm" }));
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(await screen.findByText("Đang ghi")).toBeTruthy();
    });

    it("trình duyệt chặn micro thì báo rõ và gợi ý gõ chữ", async () => {
      backend({});
      stubMic(vi.fn(async () => Promise.reject(new DOMException("denied", "NotAllowedError"))));
      open();
      fireEvent.click(await screen.findByRole("button", { name: "Bắt đầu ghi âm" }));
      fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Đồng ý ghi âm" }));
      expect((await screen.findByRole("alert")).textContent).toMatch(/không cho phép dùng micro/);
      fireEvent.click(screen.getByRole("button", { name: "Chuyển sang gõ chữ" }));
      expect(screen.getByRole("textbox", { name: /Lời giảng/ })).toBeTruthy();
    });

    it("ghi đủ 3 phút thì tự dừng, vẫn gửi được bản đã ghi", async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      backend({});
      stubMic();
      open();
      fireEvent.click(await screen.findByRole("button", { name: "Bắt đầu ghi âm" }));
      fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Đồng ý ghi âm" }));
      await screen.findByText("Đang ghi");
      const rec = FakeRecorder.instances[0];
      await act(async () => {
        await vi.advanceTimersByTimeAsync(179_000);
      });
      expect(rec.stop).not.toHaveBeenCalled();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1_500);
      });
      expect(rec.stop).toHaveBeenCalled();
      expect(screen.getByText(/Đã đủ 3 phút/)).toBeTruthy();
      expect(screen.getByText("03:00 / 03:00")).toBeTruthy();
      expect(screen.getByRole("button", { name: "Gửi bản ghi" })).toBeTruthy();
    });

    it.each([
      [422, "NO_SPEECH_DETECTED", /chưa nghe rõ lời bạn.*gõ chữ/],
      [503, "STT_UNAVAILABLE", /gõ chữ/],
    ] as const)("audio trả %i %s thì hiện câu gợi ý gõ chữ, không gửi lượt (#154)", async (status, code, text) => {
      const api = mockApi({ [audioKey]: err(status, code, "lỗi máy chủ") });
      stubMic();
      open();
      fireEvent.click(await screen.findByRole("button", { name: "Bắt đầu ghi âm" }));
      fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Đồng ý ghi âm" }));
      await screen.findByText("Đang ghi");
      fireEvent.click(screen.getByRole("button", { name: "Gửi bản ghi" }));
      const alert = await screen.findByRole("alert");
      await waitFor(() => expect(alert.textContent).toMatch(text));
      expect(alert.textContent).not.toMatch(/Máy chủ đang bận|chưa hợp lệ/);
      expect(api.called(turnsKey)).toHaveLength(0);
    });

    it("dịch vụ chép lời chưa có (501) thì báo đang phát triển, không gửi lượt", async () => {
      const api = backend({ [audioKey]: err(501, "NOT_IMPLEMENTED", "chưa làm", { card: "C1-12" }) });
      stubMic();
      open();
      fireEvent.click(await screen.findByRole("button", { name: "Bắt đầu ghi âm" }));
      fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Đồng ý ghi âm" }));
      await screen.findByText("Đang ghi");
      fireEvent.click(screen.getByRole("button", { name: "Gửi bản ghi" }));
      expect(await screen.findByText(/đang được phát triển \(thẻ C1-12\)/)).toBeTruthy();
      expect(api.called(turnsKey)).toHaveLength(0);
    });
  });
});
