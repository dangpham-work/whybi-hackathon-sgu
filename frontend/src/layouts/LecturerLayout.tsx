import { Bell, ChevronRight, Menu, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, Outlet, useLocation, useParams } from "react-router";
import { NAV } from "../lib/nav";
import { Avatar, SideNav, useCurrentScreen } from "./shell";

// TODO(GD-04): lấy người dùng từ phiên đăng nhập; tạm dùng GV mẫu trong seed/users.json
const USER = { name: "TS. Nguyễn Văn Bình", sub: "Khoa CNTT" };

/**
 * Khung web GV 1440px (Figma GV-01…GV-10): sidebar mực đậm 248px + thanh trên có breadcrumb.
 * Dưới 1024px sidebar thu vào nút menu (ngăn kéo) – dùng được từ 360px.
 */
export function LecturerLayout() {
  const { classId } = useParams();
  const screen = useCurrentScreen();
  const { pathname } = useLocation();
  const [drawer, setDrawer] = useState(false);
  useEffect(() => setDrawer(false), [pathname]);

  const items = NAV.LECTURER(classId);
  // TODO(GD-05): thay "Lớp <id>" bằng tên lớp từ API
  const crumbs: { label: string; to?: string }[] = [{ label: "Whybi AI", to: "/" }, { label: "Lớp của tôi", to: "/gv/classes" }];
  if (classId) crumbs.push({ label: `Lớp ${classId}`, to: `/gv/classes/${classId}` });
  if (screen && !["GV-01", "GV-02"].includes(screen.code)) crumbs.push({ label: screen.title });
  const nav = <SideNav roleLabel="Giảng viên" items={items} user={USER} />;

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
        <header className="flex h-16 items-center gap-3 border-b border-line-soft bg-surface px-4 lg:px-7">
          <button className="rounded-md border border-line-soft p-2 lg:hidden" aria-label="Mở menu" onClick={() => setDrawer(true)}>
            <Menu aria-hidden size={18} />
          </button>
          <nav aria-label="Đường dẫn" className="min-w-0 flex-1">
            <ol className="flex min-w-0 items-center gap-2 text-body-m text-ink-500">
              {crumbs.map((c, i) => {
                const last = i === crumbs.length - 1;
                return (
                  <li key={c.label} className={`${last ? "flex font-semibold text-ink-900" : "hidden sm:flex"} min-w-0 items-center gap-2`}>
                    {i > 0 && <ChevronRight aria-hidden size={14} className="hidden shrink-0 text-ink-300 sm:block" />}
                    {c.to && !last ? (
                      <Link to={c.to} className="truncate hover:text-teal">
                        {c.label}
                      </Link>
                    ) : (
                      <span className="truncate" aria-current={last ? "page" : undefined}>
                        {c.label}
                      </span>
                    )}
                  </li>
                );
              })}
            </ol>
          </nav>
          <label className="hidden w-64 items-center gap-2 rounded-md border border-line-strong px-3 py-2 text-body-m text-ink-300 md:flex">
            <Search aria-hidden size={16} />
            <input className="w-full bg-transparent text-ink-900 outline-none placeholder:text-ink-300" placeholder="Tìm lớp, sinh viên, nút…" aria-label="Tìm kiếm" />
          </label>
          <button className="rounded-md border border-line-soft p-2" aria-label="Thông báo">
            <Bell aria-hidden size={18} />
          </button>
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
