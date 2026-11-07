import type { ReactNode } from "react";

/** Lớp chung cho ô nhập và bảng ở các màn quản trị (GD-15). */
export const fieldCls = "w-full rounded-md border border-line-strong px-3 py-2 text-body-m focus-visible:outline-2 focus-visible:outline-teal";

export function AdminPage({ title, note, children, action }: { title: string; note?: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-h1 font-bold">{title}</h1>
          {note && <p className="text-body-m text-ink-500">{note}</p>}
        </div>
        {action}
      </header>
      {children}
    </div>
  );
}

export function Panel({ title, children, label }: { title: string; children: ReactNode; label?: string }) {
  return (
    <section aria-label={label ?? title} className="space-y-3 rounded-lg border border-line-soft bg-surface p-4">
      <h2 className="text-h3 font-semibold">{title}</h2>
      {children}
    </section>
  );
}

export const Th = ({ children, right }: { children: ReactNode; right?: boolean }) => (
  <th scope="col" className={`py-2 pr-3 text-body-s font-semibold text-ink-500 ${right ? "text-right" : "text-left"}`}>
    {children}
  </th>
);
export const Td = ({ children, right, strong }: { children: ReactNode; right?: boolean; strong?: boolean }) => (
  <td className={`border-t border-line-soft py-2 pr-3 text-body-m ${right ? "text-right" : ""} ${strong ? "font-semibold" : ""}`}>{children}</td>
);

/** Ô báo mật khẩu ban đầu: chỉ trả đúng một lần nên phải hiện nổi bật (FR-AD-03). */
export function OneTimePassword({ who, password }: { who: string; password: string }) {
  return (
    <p role="status" className="rounded-md border border-honey/50 bg-honey-soft px-3 py-2 text-body-m text-honey-deep">
      Mật khẩu ban đầu của <strong>{who}</strong>: <code className="font-bold tracking-wide">{password}</code> – chỉ hiện một lần, hãy chuyển cho người dùng ngay.
    </p>
  );
}
