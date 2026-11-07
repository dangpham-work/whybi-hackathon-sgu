/**
 * Mảnh dùng chung cho 3 layout (GD-01): sidebar mực đậm (GV, QTV), avatar chữ cái,
 * hook lấy màn đang mở từ `handle` của route.
 */
import { Link, useMatches } from "react-router";
import { Logo } from "../components/Logo";
import { isCurrent, NEED_CLASS_HINT, type NavItem } from "../lib/nav";
import type { Screen } from "../screens";

/** Màn đang mở (router gắn `handle: { screen }` cho mỗi route trong SCREENS). */
export function useCurrentScreen(): Screen | undefined {
  const matches = useMatches();
  for (let i = matches.length - 1; i >= 0; i--) {
    const h = matches[i].handle as { screen?: Screen } | undefined;
    if (h?.screen) return h.screen;
  }
  return undefined;
}

/** Chữ đầu họ + chữ đầu tên, bỏ học hàm: "TS. Nguyễn Văn Bình" → "NB". */
export const initials = (name: string) => {
  const words = name.replace(/^(TS|ThS|PGS|GS)\.\s*/u, "").split(/\s+/).filter(Boolean);
  return [words[0], words.length > 1 ? words[words.length - 1] : undefined]
    .filter((w): w is string => !!w)
    .map((w) => w[0]!.toUpperCase())
    .join("");
};

export function Avatar({ name, tone = "teal" }: { name: string; tone?: "teal" | "honey" }) {
  const cls = tone === "honey" ? "bg-honey text-ink-900" : "bg-teal-soft text-teal";
  return (
    <span aria-hidden className={`inline-flex size-9 shrink-0 items-center justify-center rounded-full text-body-s font-bold ${cls}`}>
      {initials(name)}
    </span>
  );
}

/** Sidebar 248px nền ink-900 (Figma GV-01…GV-10): logo + vai, menu, thẻ người dùng ở đáy. */
export function SideNav({ roleLabel, items, user }: { roleLabel: string; items: NavItem[]; user: { name: string; sub: string } }) {
  const current = useCurrentScreen()?.code;
  return (
    <div className="flex h-full w-62 flex-col bg-ink-900 text-white">
      <div className="flex items-center gap-3 px-6 py-6">
        <Logo />
        <div>
          <p className="text-h3 font-bold">Whybi AI</p>
          <p className="caps !text-ink-300">{roleLabel}</p>
        </div>
      </div>
      <nav aria-label="Điều hướng chính" className="px-4">
        <ul className="flex flex-col gap-1">
          {items.map((item) => {
            const { to, label, icon: Icon } = item;
            const active = isCurrent(item, current);
            return (
              <li key={label}>
                {to ? (
                  <Link
                    to={to}
                    aria-current={active ? "page" : undefined}
                    className={`flex items-center gap-3 rounded-md px-4 py-2.5 text-body-m outline-honey focus-visible:outline-2 ${
                      active ? "bg-white/10 font-semibold text-white" : "text-ink-300 hover:bg-white/5 hover:text-white"
                    }`}
                  >
                    <Icon aria-hidden size={18} className={`shrink-0 ${active ? "text-honey" : ""}`} />
                    {label}
                  </Link>
                ) : (
                  <span aria-disabled="true" title={NEED_CLASS_HINT} className="flex cursor-not-allowed items-center gap-3 px-4 py-2.5 text-body-m text-ink-500">
                    <Icon aria-hidden size={18} className="shrink-0" />
                    {label}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="mt-auto flex items-center gap-3 border-t border-white/10 px-4 py-4">
        <Avatar name={user.name} tone="honey" />
        <div className="min-w-0">
          <p className="truncate text-body-m font-semibold">{user.name}</p>
          <p className="truncate text-body-s text-ink-300">{user.sub}</p>
        </div>
      </div>
    </div>
  );
}
