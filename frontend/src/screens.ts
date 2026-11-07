/**
 * Danh mục màn hình – Bảng 5.12 đề cương + màn bổ sung (Bảng 4 kế hoạch phân công).
 * Nguồn duy nhất cho router, menu và trang giữ chỗ. Figma: tệp XtHQ0l4kAXNYzTb3v8iKDV.
 * Ảnh tham chiếu từng màn: docs/design/screens/<code>.png
 */
export type Role = "LECTURER" | "STUDENT" | "ADMIN" | "PUBLIC";

export interface Screen {
  code: string;
  title: string;
  path: string;
  role: Role;
  card: string; // thẻ việc giao diện (GD-xx)
  round: 1 | 2 | 3;
  reqs: string;
  figmaNode?: string;
}

export const FIGMA_FILE = "https://www.figma.com/design/XtHQ0l4kAXNYzTb3v8iKDV/Untitled";
export const figmaUrl = (node?: string) => (node ? `${FIGMA_FILE}?node-id=${node.replace(":", "-")}` : FIGMA_FILE);

export const SCREENS: Screen[] = [
  // --- Bổ sung: xác thực (FR-AD-01) ---
  { code: "AUTH-01", title: "Đăng nhập", path: "/login", role: "PUBLIC", card: "GD-04", round: 1, reqs: "FR-AD-01" },
  { code: "AUTH-02", title: "Quên mật khẩu", path: "/forgot-password", role: "PUBLIC", card: "GD-04", round: 1, reqs: "FR-AD-01" },

  // --- Giảng viên – Web 1440px ---
  { code: "GV-01", title: "Danh sách lớp", path: "/gv/classes", role: "LECTURER", card: "GD-05", round: 1, reqs: "FR-SK-01", figmaNode: "14:699" },
  { code: "GV-02", title: "Tổng quan lớp", path: "/gv/classes/:classId", role: "LECTURER", card: "GD-05", round: 1, reqs: "FR-SK-01", figmaNode: "14:1122" },
  { code: "GV-03", title: "Tải giáo trình & tiến độ", path: "/gv/classes/:classId/syllabus", role: "LECTURER", card: "GD-05", round: 1, reqs: "FR-SK-02, FR-SK-03", figmaNode: "14:1468" },
  { code: "GV-04", title: "Trình sửa cây & rubric", path: "/gv/classes/:classId/tree", role: "LECTURER", card: "GD-09", round: 1, reqs: "FR-SK-04…10", figmaNode: "17:1065" },
  { code: "GV-05", title: "Dashboard bản đồ nhiệt", path: "/gv/classes/:classId/heatmap", role: "LECTURER", card: "GD-10", round: 1, reqs: "FR-HM-01…05, 09, 10", figmaNode: "17:1447" },
  { code: "GV-06", title: "Chi tiết nút & điểm nghẽn", path: "/gv/classes/:classId/nodes/:nodeId", role: "LECTURER", card: "GD-10", round: 1, reqs: "FR-HM-06", figmaNode: "19:1460" },
  { code: "GV-07", title: "Hồ sơ năng lực SV", path: "/gv/classes/:classId/students/:studentId", role: "LECTURER", card: "GD-13", round: 2, reqs: "FR-HM-07", figmaNode: "19:1885" },
  { code: "GV-08", title: "Transcript & ghi âm", path: "/gv/sessions/:sessionId", role: "LECTURER", card: "GD-13", round: 2, reqs: "FR-HM-07, FR-TB-14", figmaNode: "19:2212" },
  { code: "GV-09", title: "Quản lý ghép cặp", path: "/gv/classes/:classId/matching", role: "LECTURER", card: "GD-11", round: 1, reqs: "FR-PM-01…08", figmaNode: "19:2649" },
  { code: "GV-10", title: "Cấu hình ngưỡng", path: "/gv/classes/:classId/settings", role: "LECTURER", card: "GD-14", round: 2, reqs: "FR-HM-08", figmaNode: "19:2959" },

  // --- Sinh viên – Mobile 390px ---
  { code: "SV-01", title: "Danh sách lớp / nhập mã", path: "/sv/classes", role: "STUDENT", card: "GD-04", round: 1, reqs: "FR-TB-01", figmaNode: "25:482" },
  { code: "SV-02", title: "Bản đồ học tập", path: "/sv/classes/:classId", role: "STUDENT", card: "GD-06", round: 1, reqs: "FR-TB-01", figmaNode: "25:714" },
  { code: "SV-03", title: "Chi tiết nút", path: "/sv/classes/:classId/nodes/:nodeId", role: "STUDENT", card: "GD-06", round: 1, reqs: "FR-TB-02", figmaNode: "25:826" },
  { code: "SV-04", title: "Phiên giảng lại", path: "/sv/sessions/:sessionId", role: "STUDENT", card: "GD-07", round: 1, reqs: "FR-TB-03…05, 08, 10, 11", figmaNode: "25:1214" },
  { code: "SV-05", title: "Xác nhận bản chép lời", path: "/sv/sessions/:sessionId/transcript", role: "STUDENT", card: "GD-08", round: 1, reqs: "FR-TB-06, 07", figmaNode: "25:1280" },
  { code: "SV-06", title: "Kết quả & phản hồi", path: "/sv/sessions/:sessionId/result", role: "STUDENT", card: "GD-08", round: 1, reqs: "FR-TB-13", figmaNode: "25:1410" },
  { code: "SV-07", title: "Bạn cùng tiến", path: "/sv/classes/:classId/peers", role: "STUDENT", card: "GD-11", round: 1, reqs: "FR-PM-01, 05, 06, 07", figmaNode: "25:1602" },
  { code: "SV-08", title: "Lịch sử phiên", path: "/sv/history", role: "STUDENT", card: "GD-16", round: 3, reqs: "FR-TB-15", figmaNode: "25:1031" },

  // --- Chung ---
  { code: "ME-01", title: "Hồ sơ cá nhân", path: "/me", role: "PUBLIC", card: "GD-04", round: 1, reqs: "FR-AD-01" },

  // --- Bổ sung: Quản trị (FR-AD-03…08) – chưa có trong Bảng 5.12 / Figma ---
  { code: "AD-01", title: "Tài khoản & nhập CSV", path: "/admin/users", role: "ADMIN", card: "GD-15", round: 2, reqs: "FR-AD-03" },
  { code: "AD-02", title: "Danh mục môn học", path: "/admin/courses", role: "ADMIN", card: "GD-15", round: 2, reqs: "FR-AD-04" },
  { code: "AD-03", title: "Cấu hình nhà cung cấp AI", path: "/admin/ai-config", role: "ADMIN", card: "GD-15", round: 2, reqs: "FR-AD-05" },
  { code: "AD-04", title: "Hạn mức", path: "/admin/quotas", role: "ADMIN", card: "GD-15", round: 2, reqs: "FR-AD-06" },
  { code: "AD-05", title: "Nhật ký & cờ vi phạm", path: "/admin/flags", role: "ADMIN", card: "GD-15", round: 2, reqs: "FR-AD-07" },
];
