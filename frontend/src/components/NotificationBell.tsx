import { Bell, CheckCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { apiCall, type Schema } from "../lib/api";
import { useCurrentUser } from "../lib/auth";
import { useChannel } from "../lib/ws";

type Notice = Schema<"NotificationOut">;

/** Chuông thông báo trong ứng dụng (FR-AD-08, GD-15): tải danh sách, nhận thông báo mới qua kênh `user:{id}`, đánh dấu đã đọc. */
export function NotificationBell() {
  const user = useCurrentUser();
  const [items, setItems] = useState<Notice[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!user) return;
    const ctrl = new AbortController();
    apiCall("get", "/notifications", { signal: ctrl.signal }).then(setItems, () => {}); // lỗi mạng: chuông vẫn dùng được, chỉ chưa có danh sách
    return () => ctrl.abort();
  }, [user]);

  useChannel(user ? `user:${user.id}` : null, (e) => {
    if (e.event !== "notification") return;
    const n = e.payload as Notice;
    setItems((list) => [n, ...list.filter((x) => x.id !== n.id)]);
  });

  const unread = items.filter((n) => !n.isRead).length;
  const markRead = (id: string) => {
    setItems((l) => l.map((n) => (n.id === id ? { ...n, isRead: true } : n)));
    void apiCall("post", "/notifications/{notification_id}/read", { path: { notification_id: id } }).catch(() => {});
  };
  const markAll = () => {
    setItems((l) => l.map((n) => ({ ...n, isRead: true })));
    void apiCall("post", "/notifications/read-all").catch(() => {});
  };

  return (
    <div className="relative">
      <button
        className="relative rounded-md border border-line-soft p-2"
        aria-label={unread ? `Thông báo, ${unread} chưa đọc` : "Thông báo"}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <Bell aria-hidden size={18} />
        {unread > 0 && <span aria-hidden className="absolute -right-1 -top-1 min-w-4 rounded-full bg-red-600 px-1 text-center text-caps font-bold text-white">{unread}</span>}
      </button>
      {open && (
        <div role="dialog" aria-label="Thông báo" className="absolute right-0 z-30 mt-2 w-80 max-w-[90vw] space-y-1 rounded-lg border border-line-soft bg-surface p-2 shadow-dialog">
          <div className="flex items-center justify-between px-2 py-1">
            <h2 className="font-semibold">Thông báo</h2>
            {unread > 0 && (
              <button onClick={markAll} className="inline-flex items-center gap-1 text-body-s font-semibold text-teal">
                <CheckCheck aria-hidden size={14} /> Đọc hết
              </button>
            )}
          </div>
          {items.length === 0 && <p className="px-2 py-3 text-body-m text-ink-500">Chưa có thông báo nào.</p>}
          <ul className="max-h-80 overflow-y-auto">
            {items.map((n) => {
              const body = (
                <>
                  <span className="flex items-center gap-2 font-semibold">
                    {!n.isRead && <span aria-label="Chưa đọc" className="size-2 rounded-full bg-teal" />}
                    {n.title}
                  </span>
                  {n.content && <span className="block text-body-s text-ink-500">{n.content}</span>}
                </>
              );
              return (
                <li key={n.id} className={`rounded-md px-2 py-2 ${n.isRead ? "" : "bg-teal-soft/50"}`}>
                  {n.link ? (
                    <Link to={n.link} onClick={() => { markRead(n.id); setOpen(false); }}>{body}</Link>
                  ) : (
                    <button className="w-full text-left" onClick={() => markRead(n.id)}>{body}</button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
