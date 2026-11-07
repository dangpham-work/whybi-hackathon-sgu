/**
 * Hook tải dữ liệu dùng chung (GD-02): trạng thái loading / success / error, tự hủy yêu cầu cũ, gọi lại được.
 *   const tree = useApi((signal) => apiCall("get", "/classes/{class_id}/tree", { path: { class_id }, signal }), [class_id]);
 *   <AsyncView state={tree}>{(t) => <SkillTree … nodes={t.nodes} edges={t.edges} />}</AsyncView>
 */
import { useCallback, useEffect, useRef, useState, type DependencyList } from "react";

export type AsyncState<T> =
  | { status: "loading"; data?: T; error?: undefined; reload: () => void }
  | { status: "success"; data: T; error?: undefined; reload: () => void }
  | { status: "error"; data?: T; error: unknown; reload: () => void };

export function useApi<T>(load: (signal: AbortSignal) => Promise<T>, deps: DependencyList): AsyncState<T> {
  const [state, setState] = useState<{ status: AsyncState<T>["status"]; data?: T; error?: unknown }>({ status: "loading" });
  const [tick, setTick] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    const ctrl = new AbortController();
    setState((s) => ({ status: "loading", data: s.data }));
    loadRef.current(ctrl.signal).then(
      (data) => !ctrl.signal.aborted && setState({ status: "success", data }),
      (error: unknown) => !ctrl.signal.aborted && setState((s) => ({ status: "error", data: s.data, error })),
    );
    return () => ctrl.abort();
    // deps do bên gọi quyết định, giống useEffect; `load` đọc qua ref nên không cần nằm trong deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload } as AsyncState<T>;
}
