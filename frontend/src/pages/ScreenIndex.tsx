import { Link } from "react-router";
import { Logo } from "../components/Logo";
import { StatusLegend } from "../components/StatusBadge";
import { SCREENS } from "../screens";

const sample = (path: string) => path.replace(":classId", "demo").replace(/:\w+/g, "demo");

/** Mục lục màn hình cho cả đội trong lúc phát triển (thay bằng điều hướng theo vai sau khi có GD-04). */
export function ScreenIndex() {
  const groups = [
    ["Giảng viên – Web", "LECTURER"],
    ["Sinh viên – Mobile", "STUDENT"],
    ["Quản trị", "ADMIN"],
    ["Chung", "PUBLIC"],
  ] as const;
  return (
    <div className="mx-auto max-w-5xl p-8">
      <div className="flex items-center gap-3">
        <Logo size={40} />
        <div>
          <h1 className="text-display font-bold">Whybi AI</h1>
          <p className="text-body-m text-ink-500">Nền tảng học tập “Sinh viên làm thầy, AI làm học trò” – đội WhyBloom</p>
        </div>
      </div>
      <div className="mt-6 space-y-2">
        <StatusLegend kind="heat" />
        <StatusLegend kind="mastery" />
      </div>
      {groups.map(([title, role]) => (
        <section key={role} className="mt-8">
          <h2 className="text-h2 font-semibold">{title}</h2>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {SCREENS.filter((s) => s.role === role).map((s) => (
              <li key={s.code}>
                <Link to={sample(s.path)} className="block rounded-md border border-line-soft bg-surface px-4 py-3 shadow-card hover:border-teal">
                  <span className="font-semibold">{s.code}</span> · {s.title}
                  <span className="float-right text-body-s text-ink-500">
                    {s.card} · V{s.round}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
