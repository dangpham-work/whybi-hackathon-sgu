/**
 * Menu theo vai – sơ đồ điều hướng 5.5.1 (docs/diagrams/59_screen_flow.puml). Thẻ GD-01.
 * Layout chỉ đọc dữ liệu ở đây; thêm / đổi mục menu thì sửa file này (test: src/test/layouts.test.tsx).
 */
import {
  BookOpen,
  Bot,
  Flag,
  Flame,
  Gauge,
  History,
  LayoutGrid,
  Network,
  Settings,
  User,
  Users,
  UserCog,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  icon: LucideIcon;
  /** null = chưa đủ ngữ cảnh (vd. GV chưa chọn lớp) → hiện mục bị khóa kèm lời nhắc */
  to: string | null;
  /** mã màn (src/screens.ts) làm mục này sáng – vd. GV-06 chi tiết nút thuộc nhánh "Bản đồ nhiệt" */
  screens: string[];
}

export const NEED_CLASS_HINT = "Chọn một lớp trước";

const inClass = (classId: string | undefined, sub: string) => (classId ? `/gv/classes/${classId}${sub}` : null);

/** Mục menu có sáng với màn đang mở không. */
export const isCurrent = (item: NavItem, screenCode?: string) => !!screenCode && item.screens.includes(screenCode);

export const NAV = {
  /** Sidebar GV: GV-01 → GV-02 → GV-04 / GV-05 / GV-09 / GV-10 */
  LECTURER: (classId?: string): NavItem[] => [
    { label: "Lớp của tôi", icon: LayoutGrid, to: "/gv/classes", screens: ["GV-01", "GV-02", "GV-03"] },
    { label: "Cây kỹ năng", icon: Network, to: inClass(classId, "/tree"), screens: ["GV-04"] },
    { label: "Bản đồ nhiệt", icon: Flame, to: inClass(classId, "/heatmap"), screens: ["GV-05", "GV-06", "GV-07", "GV-08"] },
    { label: "Ghép cặp", icon: Users, to: inClass(classId, "/matching"), screens: ["GV-09"] },
    { label: "Cấu hình", icon: Settings, to: inClass(classId, "/settings"), screens: ["GV-10"] },
  ],
  /** Thanh tab dưới SV: SV-02 · SV-07 · SV-08 · Hồ sơ */
  STUDENT: (classId?: string): NavItem[] => [
    { label: "Bản đồ", icon: Network, to: classId ? `/sv/classes/${classId}` : "/sv/classes", screens: ["SV-01", "SV-02", "SV-03", "SV-04", "SV-05", "SV-06"] },
    { label: "Bạn cùng tiến", icon: Users, to: classId ? `/sv/classes/${classId}/peers` : null, screens: ["SV-07"] },
    { label: "Lịch sử", icon: History, to: "/sv/history", screens: ["SV-08"] },
    { label: "Hồ sơ", icon: User, to: "/me", screens: ["ME-01"] },
  ],
  /** Sidebar QTV (bổ sung – FR-AD-03…08) */
  ADMIN: (): NavItem[] => [
    { label: "Tài khoản & nhập CSV", icon: UserCog, to: "/admin/users", screens: ["AD-01"] },
    { label: "Danh mục môn học", icon: BookOpen, to: "/admin/courses", screens: ["AD-02"] },
    { label: "Cấu hình nhà cung cấp AI", icon: Bot, to: "/admin/ai-config", screens: ["AD-03"] },
    { label: "Hạn mức", icon: Gauge, to: "/admin/quotas", screens: ["AD-04"] },
    { label: "Nhật ký & cờ vi phạm", icon: Flag, to: "/admin/flags", screens: ["AD-05"] },
  ],
} as const;
