import { AlertTriangle, Loader2, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { errorMessage } from "../lib/api";
import type { AsyncState } from "../lib/hooks";
import { Button } from "./Button";

/** Trạng thái đang tải – có biểu tượng + chữ, đọc được bằng trình đọc màn hình. */
export function Loading({ label = "Đang tải…" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-2 p-4 text-body-m text-ink-500">
      <Loader2 size={18} className="animate-spin" aria-hidden />
      <span>{label}</span>
    </div>
  );
}

/** Hộp báo lỗi dễ hiểu (GD-02), kèm nút "Thử lại" nếu có. */
export function ErrorNotice({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-md border border-st-fail bg-surface p-4 text-body-m text-ink-900">
      <AlertTriangle size={18} className="shrink-0 text-st-fail" aria-hidden />
      <span className="flex-1">{errorMessage(error)}</span>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          <RefreshCw size={16} aria-hidden /> Thử lại
        </Button>
      )}
    </div>
  );
}

type Props<T> = {
  state: AsyncState<T>;
  children: (data: T) => ReactNode;
  loadingLabel?: string;
  /** Hiện khi dữ liệu rỗng (mảng rỗng / null). */
  empty?: ReactNode;
};

/** Gói chung 3 trạng thái tải / lỗi / có dữ liệu cho mọi màn. */
export function AsyncView<T>({ state, children, loadingLabel, empty }: Props<T>) {
  if (state.error) return <ErrorNotice error={state.error} onRetry={state.reload} />;
  if (state.loading && state.data === undefined) return <Loading label={loadingLabel} />;
  const d = state.data;
  if (d === undefined || d === null || (Array.isArray(d) && d.length === 0)) {
    return <>{empty ?? <p className="p-4 text-body-m text-ink-500">Chưa có dữ liệu.</p>}</>;
  }
  return <>{children(d)}</>;
}
