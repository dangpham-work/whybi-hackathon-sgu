/**
 * Quy ước trực quan – Hình 5.23 / Figma mục 05. Mọi màu LUÔN kèm biểu tượng (NFR-12):
 * người mù màu đỏ–lục vẫn phân biệt được.
 */
import { Check, CircleSlash, Ellipsis, Circle, RotateCcw, X, TriangleAlert, Target, type LucideIcon } from "lucide-react";

export type MasteryState = "LOCKED" | "AVAILABLE" | "IN_PROGRESS" | "MASTERED" | "NOT_PASSED" | "NEEDS_REVERIFY";
export type HeatColor = "GREY" | "GREEN" | "YELLOW" | "RED";

interface Look {
  label: string;
  icon: LucideIcon;
  className: string; // nền + chữ + viền
}

export const MASTERY: Record<MasteryState, Look> = {
  MASTERED: { label: "Đạt", icon: Check, className: "bg-st-pass text-green-900 border-green-700/40" },
  NOT_PASSED: { label: "Chưa đạt", icon: X, className: "bg-st-fail text-red-900 border-red-700/40" },
  IN_PROGRESS: { label: "Đang giảng", icon: Ellipsis, className: "bg-st-warn text-yellow-900 border-yellow-700/40" },
  AVAILABLE: { label: "Sẵn sàng", icon: Circle, className: "bg-surface text-ink-700 border-line-strong" },
  LOCKED: { label: "Khóa", icon: CircleSlash, className: "bg-st-grey text-ink-500 border-line-strong" },
  NEEDS_REVERIFY: { label: "Cần xác nhận lại", icon: RotateCcw, className: "bg-st-reverify text-orange-900 border-orange-700/40" },
};

export const HEAT: Record<HeatColor, Look> = {
  GREEN: { label: "Đạt ≥ 70%", icon: Check, className: "bg-st-pass text-green-900 border-green-700/40" },
  YELLOW: { label: "40–70%", icon: TriangleAlert, className: "bg-st-warn text-yellow-900 border-yellow-700/40" },
  RED: { label: "< 40%", icon: X, className: "bg-st-fail text-red-900 border-red-700/40" },
  GREY: { label: "Chưa đủ mẫu", icon: Circle, className: "bg-st-grey text-ink-500 border-line-strong" },
};

/** ◎ GỐC – điểm nghẽn gốc (viền đậm, nhấp nháy) */
export const ROOT_CAUSE: Look = { label: "Điểm nghẽn gốc", icon: Target, className: "bg-ink-900 text-honey border-ink-900" };
