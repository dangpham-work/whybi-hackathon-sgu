import { Bell } from "lucide-react";
import { Link, Outlet, useParams } from "react-router";
import { Logo } from "../components/Logo";
import { isCurrent, NAV, NEED_CLASS_HINT } from "../lib/nav";
import { Avatar, useCurrentScreen } from "./shell";

// TODO(GD-04): lấy người dùng từ phiên đăng nhập; tạm dùng SV mẫu trong seed/users.json
const USER = { name: "Trần Bảo Châu" };

/** Khung mobile SV 390px (Figma SV-01…SV-08): header trắng + thanh tab dưới. Responsive từ 360px (NFR-11). */
export function StudentLayout() {
  const { classId } = useParams();
  const screen = useCurrentScreen();
  const tabs = NAV.STUDENT(classId);
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-[480px] flex-col bg-app">
      <header className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-line-soft bg-surface px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <Logo size={32} />
          <div className="min-w-0">
            {/* TODO(GD-06): tên lớp từ API ở SV-02/SV-03 */}
            <p className="truncate text-h3 font-bold">{screen?.title ?? "Whybi AI"}</p>
            <p className="truncate text-body-s text-ink-500">Whybi AI · Sinh viên</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button className="rounded-full bg-app p-2" aria-label="Thông báo">
            <Bell aria-hidden size={18} />
          </button>
          <Link to="/me" aria-label="Hồ sơ cá nhân">
            <Avatar name={USER.name} />
          </Link>
        </div>
      </header>
      <main className="flex-1 p-4 pb-24">
        <Outlet />
      </main>
      <nav aria-label="Điều hướng chính" className="fixed inset-x-0 bottom-0 z-10 mx-auto max-w-[480px] border-t border-line-soft bg-surface pb-[env(safe-area-inset-bottom)]">
        <ul className="grid grid-cols-4 py-2">
          {tabs.map((tab) => {
            const { to, label, icon: Icon } = tab;
            const active = isCurrent(tab, screen?.code);
            return (
              <li key={label}>
                {to ? (
                  <Link
                    to={to}
                    aria-current={active ? "page" : undefined}
                    className={`flex flex-col items-center gap-1 py-1 text-body-s ${active ? "font-semibold text-teal" : "text-ink-500"}`}
                  >
                    <Icon aria-hidden size={20} />
                    {label}
                  </Link>
                ) : (
                  <span aria-disabled="true" title={NEED_CLASS_HINT} className="flex cursor-not-allowed flex-col items-center gap-1 py-1 text-body-s text-ink-300">
                    <Icon aria-hidden size={20} />
                    {label}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
