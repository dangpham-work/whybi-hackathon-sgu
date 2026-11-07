import { Check, CircleCheck, CircleX, Clock, Hourglass, ShieldCheck, Users, type LucideIcon } from "lucide-react";
import type { Schema } from "./api";

export type MatchOut = Schema<"MatchOut">;
export type MatchStatus = MatchOut["status"];

interface Look {
  label: string;
  icon: LucideIcon;
  className: string;
}

/** Trạng thái cặp (Hình 4.30): luôn kèm biểu tượng + chữ (NFR-12). */
export const MATCH_STATUS: Record<MatchStatus, Look> = {
  PROPOSED: { label: "Chờ phản hồi", icon: Clock, className: "bg-honey-soft text-honey-deep border-honey/50" },
  WAITING_OTHER: { label: "Chờ bạn phản hồi", icon: Hourglass, className: "bg-honey-soft text-honey-deep border-honey/50" },
  ACCEPTED: { label: "Đã chấp nhận", icon: Check, className: "bg-st-pass text-green-900 border-green-700/40" },
  STUDIED: { label: "Đã học cùng", icon: Users, className: "bg-st-pass text-green-900 border-green-700/40" },
  VERIFIED: { label: "Đã xác nhận lại Đạt", icon: ShieldCheck, className: "bg-st-pass text-green-900 border-green-700/40" },
  PARTIALLY_VERIFIED: { label: "Xác nhận lại một phần", icon: CircleCheck, className: "bg-st-warn text-yellow-900 border-yellow-700/40" },
  UNVERIFIED: { label: "Chưa xác nhận lại Đạt", icon: CircleX, className: "bg-st-warn text-yellow-900 border-yellow-700/40" },
  DECLINED: { label: "Đã từ chối", icon: CircleX, className: "bg-st-grey text-ink-500 border-line-strong" },
  EXPIRED: { label: "Hết hạn", icon: CircleX, className: "bg-st-grey text-ink-500 border-line-strong" },
};

/** Cặp còn hoạt động (chưa kết thúc) – dùng cho "cặp đang hoạt động" ở GV-09. */
export const isActive = (s: MatchStatus) => !["DECLINED", "EXPIRED", "VERIFIED", "PARTIALLY_VERIFIED", "UNVERIFIED"].includes(s);

/** "còn 41 giờ" / "còn 5 ngày" / "đã hết hạn" tính từ `expiresAt` (BR-09). */
export function remaining(expiresAt: string, now = Date.now()): string {
  const ms = new Date(expiresAt).getTime() - now;
  if (!(ms > 0)) return "đã hết hạn";
  const hours = Math.floor(ms / 3_600_000);
  if (hours >= 48) return `còn ${Math.floor(hours / 24)} ngày`;
  return hours >= 1 ? `còn ${hours} giờ` : "còn dưới 1 giờ";
}

export const percent = (r: number) => `${Math.round(r * 100)}%`;
