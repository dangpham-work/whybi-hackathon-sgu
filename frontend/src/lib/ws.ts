/**
 * WebSocket client dùng chung (GD-02) – kênh theo Bảng 5.11:
 *   job:{jobId} · class:{id}:heatmap · user:{id} · session:{id}
 * Tự kết nối lại khi mất mạng (UC10 ngoại lệ E1) – bên dùng nên tải lại ảnh chụp khi nhận "reconnected".
 * Gọi `close()` khi không dùng nữa: client dừng hẳn, không tự nối lại (tránh chạy sau khi trang/test đã hủy).
 */
import { getToken } from "./api";

export type WsEvent = { channel: string; event: string; payload: unknown };
export type WsStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";
type Handler = (e: WsEvent) => void;

/** Tên kênh – khớp backend/app/realtime/gateway.py. */
export const channels = {
  job: (jobId: string) => `job:${jobId}`,
  heatmap: (classId: string) => `class:${classId}:heatmap`,
  user: (userId: string) => `user:${userId}`,
  session: (sessionId: string) => `session:${sessionId}`,
};

const MAX_BACKOFF = 10_000;

/** URL WebSocket theo trang hiện tại; trả null khi không có môi trường trình duyệt. */
export function defaultWsUrl(): string | null {
  if (typeof location === "undefined" || !location.host) return null;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/api/v1/ws`;
}

export class RealtimeClient {
  private ws?: WebSocket;
  private handlers = new Map<string, Set<Handler>>();
  private statusHandlers = new Set<(s: WsStatus) => void>();
  private retry = 0;
  private timer?: ReturnType<typeof setTimeout>;
  private stopped = false;
  private _status: WsStatus = "idle";

  constructor(
    private token: () => string | null = getToken,
    private url: () => string | null = defaultWsUrl,
  ) {}

  get status(): WsStatus {
    return this._status;
  }

  connect() {
    this.stopped = false;
    clearTimeout(this.timer);
    const url = this.url();
    // Môi trường đã bị hủy (rời trang, test xong) hoặc không có WebSocket: không nối.
    if (!url || typeof WebSocket === "undefined") {
      this.setStatus("closed");
      return;
    }
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return;

    this.setStatus(this.retry > 0 ? "reconnecting" : "connecting");
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.ws = ws;
    ws.onopen = () => {
      const reconnected = this.retry > 0;
      this.retry = 0;
      this.setStatus("open");
      for (const channel of this.handlers.keys()) this.send("subscribe", channel);
      if (reconnected) this.emit({ channel: "*", event: "reconnected", payload: null });
    };
    ws.onmessage = (m) => {
      let data: unknown;
      try {
        data = JSON.parse(String(m.data));
      } catch {
        return; // bỏ qua gói tin hỏng
      }
      if (data && typeof data === "object" && typeof (data as WsEvent).event === "string") {
        const e = data as Partial<WsEvent>;
        this.emit({ channel: e.channel ?? "*", event: e.event!, payload: e.payload ?? null });
      }
    };
    ws.onclose = () => {
      if (this.ws === ws) this.ws = undefined;
      this.scheduleReconnect();
    };
  }

  /** Dừng hẳn: hủy hẹn giờ nối lại, đóng socket, bỏ mọi đăng ký. */
  close() {
    this.stopped = true;
    clearTimeout(this.timer);
    this.timer = undefined;
    const ws = this.ws;
    this.ws = undefined;
    if (ws) {
      ws.onclose = null;
      ws.onmessage = null;
      ws.onopen = null;
      try {
        ws.close();
      } catch {
        /* đã đóng */
      }
    }
    this.handlers.clear();
    this.retry = 0;
    this.setStatus("closed");
  }

  subscribe(channel: string, handler: Handler): () => void {
    let set = this.handlers.get(channel);
    if (!set) {
      set = new Set();
      this.handlers.set(channel, set);
      this.send("subscribe", channel);
    }
    set.add(handler);
    return () => {
      const hs = this.handlers.get(channel);
      if (!hs) return;
      hs.delete(handler);
      if (hs.size === 0) {
        this.handlers.delete(channel);
        this.send("unsubscribe", channel);
      }
    };
  }

  /** Theo dõi trạng thái kết nối (hiện "Đang kết nối lại…" trên giao diện). */
  onStatus(handler: (s: WsStatus) => void): () => void {
    this.statusHandlers.add(handler);
    return () => this.statusHandlers.delete(handler);
  }

  private scheduleReconnect() {
    if (this.stopped || this.url() === null || typeof WebSocket === "undefined") {
      this.setStatus("closed");
      return;
    }
    this.setStatus("reconnecting");
    const delay = Math.min(1000 * 2 ** this.retry++, MAX_BACKOFF);
    clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.timer = undefined;
      if (!this.stopped) this.connect();
    }, delay);
  }

  private send(action: "subscribe" | "unsubscribe", channel: string) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action, channel, token: this.token() }));
    }
  }

  private setStatus(s: WsStatus) {
    if (this._status === s) return;
    this._status = s;
    this.statusHandlers.forEach((h) => h(s));
  }

  private emit(e: WsEvent) {
    for (const [ch, hs] of this.handlers) {
      if (ch === e.channel || e.channel === "*") hs.forEach((h) => h(e));
    }
  }
}

let shared: RealtimeClient | null = null;

/** Client dùng chung cho cả ứng dụng (một kết nối duy nhất), nối khi gọi lần đầu. */
export function getRealtime(): RealtimeClient {
  if (!shared) {
    shared = new RealtimeClient();
    shared.connect();
  }
  return shared;
}

/** Đóng client dùng chung (đăng xuất, test). */
export function closeRealtime() {
  shared?.close();
  shared = null;
}
