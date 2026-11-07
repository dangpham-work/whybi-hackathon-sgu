import { useEffect, useState } from "react";

/**
 * Đếm ngược tới `deadline` (ISO, FR-TB-11). Trả số giây còn lại (làm tròn lên) hoặc null khi không có hạn.
 * Máy chủ vẫn là bên quyết định hết giờ (C1-15, có thời gian châm chước); đồng hồ chỉ để SV nhìn và gọi /timeout đúng lúc.
 */
export function useCountdown(deadline: string | null | undefined, now: () => number = Date.now): number | null {
  const left = () => (deadline ? Math.max(0, Math.ceil((new Date(deadline).getTime() - now()) / 1000)) : null);
  // Lưu kèm hạn mà giá trị thuộc về: sang câu mới (hạn mới) thì không được trả nhầm số 0 của câu cũ trong lúc chờ effect chạy.
  const [state, setState] = useState({ deadline, seconds: left() });
  useEffect(() => {
    setState({ deadline, seconds: left() });
    if (!deadline) return;
    const t = setInterval(() => setState({ deadline, seconds: left() }), 250);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deadline]);
  return state.deadline === deadline ? state.seconds : left();
}

/** 95 → "01:35". */
export const mmss = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
