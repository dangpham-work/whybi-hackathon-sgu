/**
 * Đo sự kiện dán và tốc độ gõ của ô nhập lời giảng (FR-TB-04, GD-07) – gửi kèm Turn để C1-08 / Guard
 * gắn cờ "dán bất thường" (FR-TB-14).
 *
 *   pasteRatio = ký tự dán / (ký tự dán + ký tự gõ tay)   ∈ [0, 1]
 *   typingCps  = ký tự gõ tay / giây gõ thật                ≥ 0
 *
 * "Giây gõ thật": cộng khoảng cách giữa hai lần gõ liên tiếp, mỗi khoảng tối đa PAUSE_CAP_MS –
 * SV dừng lại suy nghĩ lâu không làm tốc độ gõ tụt về gần 0.
 * Ký tự xóa không trừ vào số đã gõ (đo hành vi nhập, không đo nội dung cuối).
 */
export const PAUSE_CAP_MS = 2_000;

export interface TypingSnapshot {
  pasteRatio: number;
  typingCps: number;
}

export interface TypingMeter {
  /** Gọi ở onPaste với số ký tự trong clipboard – lần change kế tiếp được tính là dán. */
  paste(length: number): void;
  /** Gọi ở onChange với giá trị cũ và mới. */
  change(prev: string, next: string): void;
  snapshot(): TypingSnapshot;
  reset(): void;
}

export function createTypingMeter(now: () => number = () => performance.now()): TypingMeter {
  let pasted = 0;
  let typed = 0;
  let activeMs = 0;
  let lastTypedAt: number | undefined;
  let pendingPaste = 0;

  return {
    paste(length) {
      pendingPaste += Math.max(0, length);
    },
    change(prev, next) {
      const added = Math.max(0, next.length - prev.length);
      if (pendingPaste > 0) {
        // dán đè lên đoạn đang chọn thì độ dài tăng ít hơn clipboard – vẫn tính đủ số ký tự đã dán
        pasted += pendingPaste;
        pendingPaste = 0;
        return;
      }
      if (added === 0) return;
      const t = now();
      if (lastTypedAt !== undefined) activeMs += Math.min(t - lastTypedAt, PAUSE_CAP_MS);
      lastTypedAt = t;
      typed += added;
    },
    snapshot() {
      const total = pasted + typed;
      const pasteRatio = total === 0 ? 0 : pasted / total;
      // một ký tự duy nhất (chưa có khoảng thời gian) → coi như chưa đo được
      const typingCps = typed === 0 || activeMs === 0 ? 0 : typed / (activeMs / 1000);
      return { pasteRatio, typingCps: Math.round(typingCps * 100) / 100 };
    },
    reset() {
      pasted = typed = activeMs = pendingPaste = 0;
      lastTypedAt = undefined;
    },
  };
}
