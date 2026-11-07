import type { InputHTMLAttributes, ReactNode } from "react";
import { useId } from "react";
import { Logo } from "./Logo";

/** Khung chung AUTH-01 / AUTH-02 (chưa có Figma – dựng theo token nền tảng): thẻ trắng giữa trang, logo + khẩu hiệu. */
export function AuthCard({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-app p-4">
      <div className="w-full max-w-sm rounded-lg border border-line-soft bg-surface p-6 shadow-card sm:p-8">
        <div className="flex items-center gap-3">
          <Logo size={40} />
          <div>
            <p className="text-h3 font-bold">Whybi AI</p>
            <p className="text-body-s text-ink-500">Hỏi “Tại sao” để tri thức nở rộ.</p>
          </div>
        </div>
        <h1 className="mt-6 text-h1 font-bold">{title}</h1>
        {subtitle && <p className="mt-1 text-body-m text-ink-500">{subtitle}</p>}
        <div className="mt-5">{children}</div>
      </div>
    </div>
  );
}

/** Ô nhập có nhãn caps + dòng nhắc lỗi gắn aria-describedby. */
export function Field({ label, hint, error, trailing, ...input }: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string; trailing?: ReactNode }) {
  const id = useId();
  const msgId = `${id}-msg`;
  return (
    <div>
      <label htmlFor={id} className="caps">
        {label}
      </label>
      <div className={`mt-1 flex items-center rounded-md border bg-surface focus-within:outline-2 focus-within:outline-teal ${error ? "border-red-700" : "border-line-strong"}`}>
        <input id={id} aria-invalid={!!error} aria-describedby={error || hint ? msgId : undefined} className="min-w-0 flex-1 bg-transparent px-3 py-2.5 text-body-l outline-none placeholder:text-ink-300" {...input} />
        {trailing}
      </div>
      {(error || hint) && (
        <p id={msgId} className={`mt-1 text-body-s ${error ? "text-red-900" : "text-ink-500"}`}>
          {error ?? hint}
        </p>
      )}
    </div>
  );
}

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
