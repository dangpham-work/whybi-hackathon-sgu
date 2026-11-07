import { RealtimeClient, type WsEvent } from "../lib/ws";

/** WebSocket giả: test tự mở / đóng / đẩy tin nhắn. */
class FakeSocket {
  static OPEN = 1;
  static all: FakeSocket[] = [];
  readyState = 0;
  sent: unknown[] = [];
  onopen?: () => void;
  onclose?: () => void;
  onmessage?: (m: { data: string }) => void;
  constructor(public url: string) {
    FakeSocket.all.push(this);
  }
  send(data: string) {
    this.sent.push(JSON.parse(data));
  }
  close() {
    this.readyState = 3;
    this.onclose?.();
  }
  open() {
    this.readyState = FakeSocket.OPEN;
    this.onopen?.();
  }
  push(msg: unknown) {
    this.onmessage?.({ data: typeof msg === "string" ? msg : JSON.stringify(msg) });
  }
  drop() {
    this.readyState = 3;
    this.onclose?.();
  }
}

const make = () =>
  new RealtimeClient(() => "tok", {
    url: "ws://test/api/v1/ws",
    WebSocketImpl: FakeSocket as unknown as typeof WebSocket,
  });
const latest = () => FakeSocket.all.at(-1)!;

beforeEach(() => {
  FakeSocket.all = [];
  vi.useFakeTimers();
});
afterEach(() => vi.useRealTimers());

describe("RealtimeClient (GD-02)", () => {
  it("đăng ký kênh sau khi mở kết nối, kèm token", () => {
    const rt = make();
    rt.subscribe("class:c1:heatmap", () => {});
    rt.connect();
    latest().open();
    expect(latest().url).toBe("ws://test/api/v1/ws");
    expect(latest().sent).toEqual([{ action: "subscribe", channel: "class:c1:heatmap", token: "tok" }]);
  });

  it("chuyển sự kiện đúng kênh, bỏ qua tin nhắn hỏng", () => {
    const rt = make();
    const a = vi.fn();
    const b = vi.fn();
    rt.connect();
    latest().open();
    rt.subscribe("job:1", a);
    rt.subscribe("job:2", b);
    latest().push({ channel: "job:1", event: "job.progress", payload: { pct: 40 } });
    latest().push("{không phải json");
    expect(a).toHaveBeenCalledWith({ channel: "job:1", event: "job.progress", payload: { pct: 40 } });
    expect(b).not.toHaveBeenCalled();
  });

  it("tin nhắn không có kênh (vd. lỗi từ máy chủ) đi tới mọi người nghe", () => {
    const rt = make();
    const a = vi.fn();
    rt.connect();
    latest().open();
    rt.subscribe("job:1", a);
    latest().push({ event: "error", payload: { code: "NOT_IMPLEMENTED" } });
    expect(a).toHaveBeenCalledWith(expect.objectContaining({ channel: "*", event: "error" }));
  });

  it("mất kết nối thì tự nối lại (lùi dần), đăng ký lại kênh và báo 'reconnected'", () => {
    const rt = make();
    const seen: WsEvent[] = [];
    rt.subscribe("session:s1", (e) => seen.push(e));
    rt.connect();
    latest().open();
    latest().drop();
    expect(FakeSocket.all).toHaveLength(1);
    vi.advanceTimersByTime(1000);
    expect(FakeSocket.all).toHaveLength(2);
    latest().drop(); // lần 2 lỗi ngay khi chưa mở → chờ 2 s
    vi.advanceTimersByTime(1999);
    expect(FakeSocket.all).toHaveLength(2);
    vi.advanceTimersByTime(1);
    latest().open();
    expect(latest().sent).toEqual([{ action: "subscribe", channel: "session:s1", token: "tok" }]);
    expect(seen.map((e) => e.event)).toEqual(["reconnected"]);
  });

  it("hủy đăng ký: không nhận nữa và báo máy chủ khi hết người nghe", () => {
    const rt = make();
    const a = vi.fn();
    rt.connect();
    latest().open();
    const off = rt.subscribe("user:u1", a);
    off();
    latest().push({ channel: "user:u1", event: "notification", payload: {} });
    expect(a).not.toHaveBeenCalled();
    expect(latest().sent.at(-1)).toEqual({ action: "unsubscribe", channel: "user:u1", token: "tok" });
  });

  it("close() dừng hẳn, không nối lại", () => {
    const rt = make();
    rt.connect();
    latest().open();
    rt.close();
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.all).toHaveLength(1);
  });

  it("trạng thái kết nối cho giao diện hiện 'mất kết nối'", () => {
    const rt = make();
    const states: string[] = [];
    rt.onStatus((s) => states.push(s));
    rt.connect();
    latest().open();
    latest().drop();
    expect(states).toEqual(["connecting", "open", "reconnecting"]);
  });
});
