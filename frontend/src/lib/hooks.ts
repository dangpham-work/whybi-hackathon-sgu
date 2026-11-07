/**
 * Hook dùng chung cho trạng thái tải / lỗi (GD-02).
 *   const { data, error, loading, reload } = useApi((signal) => http.get<T>("/classes", { signal }), []);
 *   useChannel(channels.heatmap(classId), (e) => …);
 */
import { useCallback, useEffect, useRef, useState, type DependencyList } from "react";
import { ApiError, errorMessage, isAbort } from "./api";
import { getRealtime, type RealtimeClient, type WsEvent } from "./ws";

export type AsyncState<T> = {
  data: T | undefined;
  /** Lỗi đã chuẩn hóa – `error.message` là câu dễ hiểu để hiện. */
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
};

function toApiError(e: unknown): ApiError {
  return e instanceof ApiError ? e : new ApiError(0, "HTTP_ERROR", errorMessage(e));
}

/** Gọi `fn` khi mount và mỗi khi `deps` đổi; tự hủy yêu cầu cũ khi rời trang hoặc gọi lại. */
export function useApi<T>(fn: (signal: AbortSignal) => Promise<T>, deps: DependencyList): AsyncState<T> {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    fnRef
      .current(ctrl.signal)
      .then((d) => {
        if (!ctrl.signal.aborted) setData(d);
      })
      .catch((e: unknown) => {
        if (!ctrl.signal.aborted && !isAbort(e)) setError(toApiError(e));
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}

/** Nghe một kênh WebSocket trong suốt vòng đời component. */
export function useChannel(
  channel: string | null | undefined,
  handler: (e: WsEvent) => void,
  client?: RealtimeClient,
) {
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    if (!channel) return;
    const c = client ?? getRealtime();
    return c.subscribe(channel, (e) => ref.current(e));
  }, [channel, client]);
}
