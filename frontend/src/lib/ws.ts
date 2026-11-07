/**
 * WebSocket client dùng chung (GD-02) – kênh theo Bảng 5.11 (backend/app/api/realtime.py):
 *   job:{jobId} · class:{id}:heatmap · user:{id} · session:{id}
 * Client gửi {"action": "subscribe" | "unsubscribe", "channel", "token"}; máy chủ đẩy {channel, event, payload}.
 * Tin nhắn không có `channel` (vd. {"event": "error", …}) được phát cho mọi người nghe với channel "*".
 * Tự kết nối lại khi mất mạng (UC10 ngoại lệ E1, lùi dần 1 s → 10 s) – bên dùng nên tải lại ảnh chụp khi nhận "reconnected".
 */
import { useEffect, useRef, useState } from "react";
import { getToken } from "./api";

export type WsEvent = { channel: string; event: string; payload: unknown };
export type WsStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";
type Handler = (e: WsEvent) => void;

export interface RealtimeOptions {
  url?: string;
  /** Thay WebSocket (test). */
  WebSocketImpl?: typeof WebSocket;
  maxDelayMs?: number;
}

const defaultUrl = () => `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/v1/ws`;

export class RealtimeClient {
  private ws?: WebSocket;
  private handlers = new Map<string, Set<Handler>>();
  private statusHandlers = new Set<(s: WsStatus) => void>();
  private retry = 0;
  private timer?: ReturnType<typeof setTimeout>;
  private stopped = false;
  status: WsStatus = "idle";

  constructor(
    private token: () => string | null,
    private opts: RealtimeOptions = {},
  ) {}

  connect() {
    this.stopped = false;
    clearTimeout(this.timer);
    // Môi trường đã bị hủy (test kết thúc / không có trình duyệt) mà timer nối lại còn treo: không có location để dựng URL.
    if (!this.opts.url && typeof location === "undefined") return;
    const Impl = this.opts.WebSocketImpl ?? WebSocket;
    this.setStatus(this.retry > 0 ? "reconnecting" : "connecting");
    const ws = new Impl(this.opts.url ?? defaultUrl());
    this.ws = ws;
    ws.onopen = () => {
      const reconnected = this.retry > 0;
      this.retry = 0;
      this.setStatus("open");
      for (const channel of this.handlers.keys()) this.send("subscribe", channel);
      if (reconnected) this.emit({ channel: "*", event: "reconnected", payload: null });
    };
    ws.onmessage = (m: MessageEvent) => {
      let msg: Partial<WsEvent>;
      try {
        msg = JSON.parse(String(m.data));
      } catch {
        return; // bỏ qua tin nhắn hỏng
      }
      if (!msg || typeof msg.event !== "string") return;
      this.emit({ channel: msg.channel ?? "*", event: msg.event, payload: msg.payload ?? null });
    };
    ws.onclose = () => {
      if (this.ws !== ws) return;
      if (this.stopped) return this.setStatus("closed");
      this.setStatus("reconnecting");
      const delay = Math.min(1000 * 2 ** this.retry++, this.opts.maxDelayMs ?? 10_000);
      this.timer = setTimeout(() => this.connect(), delay);
    };
  }

  /** Dừng hẳn (rời màn / đăng xuất) – không nối lại. */
  close() {
    this.stopped = true;
    clearTimeout(this.timer);
    this.ws?.close();
    this.setStatus("closed");
  }

  subscribe(channel: string, handler: Handler): () => void {
    if (!this.handlers.has(channel)) {
      this.handlers.set(channel, new Set());
      this.send("subscribe", channel);
    }
    this.handlers.get(channel)!.add(handler);
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

  onStatus(handler: (s: WsStatus) => void): () => void {
    this.statusHandlers.add(handler);
    return () => this.statusHandlers.delete(handler);
  }

  private setStatus(s: WsStatus) {
    if (this.status === s) return;
    this.status = s;
    this.statusHandlers.forEach((h) => h(s));
  }

  private send(action: "subscribe" | "unsubscribe", channel: string) {
    if (this.ws?.readyState === 1 /* OPEN */) {
      this.ws.send(JSON.stringify({ action, channel, token: this.token() }));
    }
  }

  private emit(e: WsEvent) {
    for (const [ch, hs] of this.handlers) if (ch === e.channel || e.channel === "*") hs.forEach((h) => h(e));
  }
}

// ---------------------------------------------------------------- dùng trong React

let shared: RealtimeClient | undefined;
/** Một kết nối cho cả ứng dụng, mở lần đầu khi có màn cần. */
export function realtime(): RealtimeClient {
  if (!shared) {
    shared = new RealtimeClient(getToken);
    shared.connect();
  }
  return shared;
}

/**
 * Nghe một kênh trong component: useChannel(`class:${id}:heatmap`, (e) => …).
 * channel = null → không nghe. Trả trạng thái kết nối để hiện "Mất kết nối – đang nối lại…".
 */
export function useChannel(channel: string | null, handler: Handler, client?: RealtimeClient): WsStatus {
  const ref = useRef(handler);
  ref.current = handler;
  const [status, setStatus] = useState<WsStatus>("idle");
  useEffect(() => {
    if (!channel) return;
    const rt = client ?? realtime();
    setStatus(rt.status);
    const offStatus = rt.onStatus(setStatus);
    const off = rt.subscribe(channel, (e) => ref.current(e));
    return () => {
      off();
      offStatus();
    };
  }, [channel, client]);
  return status;
}
