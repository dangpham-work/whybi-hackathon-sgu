import { RealtimeClient, channels, type WsStatus } from "../lib/ws";

/** WebSocket giả: test tự mở / đóng / đẩy gói tin. */
class FakeSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances: FakeSocket[] = [];

  readyState = FakeSocket.CONNECTING;
  sent: unknown[] = [];
  onopen: ((e: unknown) => void) | null = null;
  onclose: ((e: unknown) => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;

  constructor(public url: string) {
    FakeSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(JSON.parse(data));
  }
  close() {
    this.readyState = FakeSocket.CLOSED;
  }
  // điều khiển từ test
  open() {
    this.readyState = FakeSocket.OPEN;
    this.onopen?.({});
  }
  drop() {
    this.readyState = FakeSocket.CLOSED;
    this.onclose?.({});
  }
  push(data: unknown) {
    this.onmessage?.({ data: typeof data === "string" ? data : JSON.stringify(data) });
  }
}

const last = () => FakeSocket.instances[FakeSocket.instances.length - 1];
const URL = "ws://test/api/v1/ws";

describe("WebSocket client dùng chung (GD-02)", () => {
  beforeEach(() => {
    FakeSocket.instances = [];
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("đăng ký kênh kèm token sau khi mở và chuyển sự kiện đúng kênh", () => {
    const c = new RealtimeClient(() => "tok", () => URL);
    const got = vi.fn();
    const other = vi.fn();
    c.subscribe(channels.heatmap("c1"), got);
    c.subscribe(channels.job("j1"), other);
    c.connect();
    last().open();
    expect(last().url).toBe(URL);
    expect(last().sent).toEqual([
      { action: "subscribe", channel: "class:c1:heatmap", token: "tok" },
      { action: "subscribe", channel: "job:j1", token: "tok" },
    ]);
    last().push({ channel: "class:c1:heatmap", event: "heatmap.cell", payload: { x: 1 } });
    expect(got).toHaveBeenCalledWith({ channel: "class:c1:heatmap", event: "heatmap.cell", payload: { x: 1 } });
    expect(other).not.toHaveBeenCalled();
    c.close();
  });

  it("bỏ qua gói tin hỏng, không ném lỗi", () => {
    const c = new RealtimeClient(() => null, () => URL);
    const got = vi.fn();
    c.subscribe("job:1", got);
    c.connect();
    last().open();
    expect(() => last().push("không phải JSON")).not.toThrow();
    last().push({ foo: 1 });
    expect(got).not.toHaveBeenCalled();
    c.close();
  });

  it("hủy handler cuối cùng thì gửi unsubscribe", () => {
    const c = new RealtimeClient(() => "t", () => URL);
    c.connect();
    last().open();
    const off = c.subscribe("user:u1", () => {});
    off();
    expect(last().sent).toEqual([
      { action: "subscribe", channel: "user:u1", token: "t" },
      { action: "unsubscribe", channel: "user:u1", token: "t" },
    ]);
    c.close();
  });

  it("mất kết nối thì tự nối lại (lùi dần), đăng ký lại kênh và báo reconnected", () => {
    const c = new RealtimeClient(() => "t", () => URL);
    const got = vi.fn();
    const statuses: WsStatus[] = [];
    c.onStatus((s) => statuses.push(s));
    c.subscribe("session:s1", got);
    c.connect();
    last().open();
    last().drop();
    expect(FakeSocket.instances).toHaveLength(1);
    vi.advanceTimersByTime(1000);
    expect(FakeSocket.instances).toHaveLength(2);
    last().drop();
    vi.advanceTimersByTime(1999);
    expect(FakeSocket.instances).toHaveLength(2);
    vi.advanceTimersByTime(1);
    expect(FakeSocket.instances).toHaveLength(3);
    last().open();
    expect(last().sent).toContainEqual({ action: "subscribe", channel: "session:s1", token: "t" });
    expect(got).toHaveBeenCalledWith({ channel: "*", event: "reconnected", payload: null });
    expect(statuses).toEqual(["connecting", "open", "reconnecting", "open"]);
    c.close();
  });

  it("close() dừng hẳn: không nối lại dù hẹn giờ đang chờ", () => {
    const c = new RealtimeClient(() => "t", () => URL);
    c.connect();
    last().open();
    last().drop();
    c.close();
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.instances).toHaveLength(1);
    expect(c.status).toBe("closed");
  });

  it("môi trường đã bị hủy (không có URL / WebSocket) thì không nối và không ném lỗi", () => {
    const noUrl = new RealtimeClient(() => "t", () => null);
    expect(() => noUrl.connect()).not.toThrow();
    expect(noUrl.status).toBe("closed");

    // Mất URL (location đã hủy) lúc socket đóng
    let url: string | null = URL;
    const c = new RealtimeClient(() => "t", () => url);
    c.connect();
    last().open();
    url = null;
    expect(() => last().drop()).not.toThrow();
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.instances).toHaveLength(1);
    expect(c.status).toBe("closed");

    // Mất cả lớp WebSocket (môi trường test đã dọn) lúc socket đóng
    const c2 = new RealtimeClient(() => "t", () => URL);
    c2.connect();
    const sock = last();
    sock.open();
    vi.stubGlobal("WebSocket", undefined);
    expect(() => sock.drop()).not.toThrow();
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.instances).toHaveLength(2);
    expect(c2.status).toBe("closed");
  });
});
