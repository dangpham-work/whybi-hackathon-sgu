import { Construction, Inbox, LoaderCircle, LogIn, RotateCcw, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { ApiError, errorText } from "../lib/api";
import type { AsyncState } from "../lib/useApi";
import { Button } from "./Button";

/**
 * Khung hiển thị trạng thái tải / lỗi / trống / đang phát triển dùng chung (GD-02).
 * Lỗi luôn là câu dễ hiểu (lib/api.ts → FRIENDLY) kèm biểu tượng và nút "Thử lại" (NFR-12: không chỉ dựa vào màu).
 * Backend trả 501 → hộp "đang phát triển" – không giả lập dữ liệu ngầm.
 */
export function AsyncView<T>({
  state,
  children,
  isEmpty,
  empty = "Chưa có dữ liệu.",
  loadingText = "Đang tải…",
}: {
  state: AsyncState<T>;
  children: (data: T) => ReactNode;
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
  loadingText?: string;
}) {
  if (state.status === "loading" && state.data === undefined) return <LoadingBox text={loadingText} />;
  if (state.status === "error") {
    if (state.error instanceof ApiError && state.error.notImplemented) return <DevelopingBox text={state.error.message} />;
    if (state.error instanceof ApiError && state.error.status === 401) return <ErrorBox text={state.error.message} loginAgain />;
    return <ErrorBox text={errorText(state.error)} onRetry={state.reload} />;
  }
  const data = state.data as T;
  if (isEmpty?.(data)) return <EmptyBox>{empty}</EmptyBox>;
  return <>{children(data)}</>;
}

const box = "flex items-center gap-3 rounded-lg border p-4 text-body-m";

export function LoadingBox({ text = "Đang tải…" }: { text?: string }) {
  return (
    <div role="status" aria-live="polite" className={`${box} border-line-soft bg-surface text-ink-500`}>
      <LoaderCircle aria-hidden size={18} className="animate-spin text-teal" />
      {text}
    </div>
  );
}

export function ErrorBox({ text, onRetry, loginAgain }: { text: string; onRetry?: () => void; loginAgain?: boolean }) {
  return (
    <div role="alert" className={`${box} border-red-700/40 bg-st-fail/40 text-red-900`}>
      <TriangleAlert aria-hidden size={18} className="shrink-0" />
      <p className="flex-1">{text}</p>
      {loginAgain && (
        // <a> thường (không dùng Link) để ErrorBox chạy được cả ngoài router
        <a
          href={`/login?next=${encodeURIComponent(location.pathname)}`}
          className="inline-flex shrink-0 items-center gap-2 rounded-md border border-line-strong bg-surface px-4 py-2 font-semibold text-ink-900 hover:bg-app"
        >
          <LogIn aria-hidden size={16} /> Đăng nhập lại
        </a>
      )}
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          <RotateCcw aria-hidden size={16} /> Thử lại
        </Button>
      )}
    </div>
  );
}

export function DevelopingBox({ text }: { text: string }) {
  return (
    <div className={`${box} border-dashed border-line-strong bg-honey-soft text-honey-deep`}>
      <Construction aria-hidden size={18} className="shrink-0" />
      <p>{text}</p>
    </div>
  );
}

export function EmptyBox({ children }: { children: ReactNode }) {
  return (
    <div className={`${box} border-dashed border-line-strong bg-surface text-ink-500`}>
      <Inbox aria-hidden size={18} className="shrink-0" />
      <div>{children}</div>
    </div>
  );
}
