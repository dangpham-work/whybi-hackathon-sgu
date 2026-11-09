import { Menu, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router";
import { NotificationBell } from "../components/NotificationBell";
import { NAV } from "../lib/nav";
import { Avatar, BackButton, SideNav, useCurrentScreen, useShellUser } from "./shell";

/** Khung Quản trị (bổ sung – chưa có trong Figma, thẻ GD-15). Dựng theo mẫu khung GV. */
export function AdminLayout() {
  const screen = useCurrentScreen();
  const USER = useShellUser();
  const { pathname } = useLocation();
  const [drawer, setDrawer] = useState(false);
  useEffect(() => setDrawer(false), [pathname]);
  const nav = <SideNav roleLabel="Quản trị viên" items={NAV.ADMIN()} user={USER} />;

  return (
    <div className="flex min-h-screen bg-app">
      <aside className="sticky top-0 hidden h-screen shrink-0 lg:block">{nav}</aside>
      {drawer && (
        <div className="fixed inset-0 z-40 flex lg:hidden">
          <aside className="h-full shadow-dialog">{nav}</aside>
          <button className="flex-1 bg-ink-900/40" aria-label="Đóng menu" onClick={() => setDrawer(false)}>
            <X aria-hidden className="ml-auto mr-4 text-white" />
          </button>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 flex h-16 items-center gap-3 border-b border-line-soft bg-surface px-4 lg:px-7">
          <button className="rounded-md border border-line-soft p-2 lg:hidden" aria-label="Mở menu" onClick={() => setDrawer(true)}>
            <Menu aria-hidden size={18} />
          </button>
          {screen?.code !== "AD-01" && <BackButton fallback="/admin/users" />}
          <p className="min-w-0 flex-1 truncate text-body-m font-semibold">{screen?.title ?? "Quản trị"}</p>
          <NotificationBell />
          <Link to="/me" aria-label="Hồ sơ cá nhân">
            <Avatar name={USER.name} />
          </Link>
        </header>
        <main className="flex-1 p-4 lg:p-7">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
