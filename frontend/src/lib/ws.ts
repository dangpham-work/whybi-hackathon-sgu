/**
 * WebSocket client dùng chung (GD-02) – kênh theo Bảng 5.11:
 *   job:{jobId} · class:{id}:heatmap · user:{id} · session:{id}
 * Tự kết nối lại khi mất mạng (UC10 ngoại lệ E1) – bên dùng nên tải lại ảnh chụp khi nhận "reconnected".
 */
export type WsEvent = { channel: string; event: string; payload: unknown };
type Handler = (e: WsEvent) => void;

export class RealtimeClient {
  private ws?: WebSocket;
  private handlers = new Map<string, Set<Handler>>();
  private retry = 0;

  constructor(private token: () => string | null) {}

  connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    this.ws = new WebSocket(`${proto}://${location.host}/api/v1/ws`);
    this.ws.onopen = () => {
      const reconnected = this.retry > 0;
      this.retry = 0;
      for (const channel of this.handlers.keys()) this.send(channel);
      if (reconnected) this.emit({ channel: "*", event: "reconnected", payload: null });
    };
    this.ws.onmessage = (m) => this.emit(JSON.parse(m.data) as WsEvent);
    this.ws.onclose = () => setTimeout(() => this.connect(), Math.min(1000 * 2 ** this.retry++, 10_000));
  }

  subscribe(channel: string, handler: Handler): () => void {
    if (!this.handlers.has(channel)) {
      this.handlers.set(channel, new Set());
      this.send(channel);
    }
    this.handlers.get(channel)!.add(handler);
    return () => this.handlers.get(channel)?.delete(handler);
  }

  private send(channel: string) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: "subscribe", channel, token: this.token() }));
    }
  }

  private emit(e: WsEvent) {
    for (const [ch, hs] of this.handlers) if (ch === e.channel || e.channel === "*") hs.forEach((h) => h(e));
  }
}
