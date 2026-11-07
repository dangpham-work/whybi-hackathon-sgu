/**
 * Lớp gọi API dùng chung (GD-02). Kiểu dữ liệu sinh tự động từ OpenAPI của backend:
 *   npm run gen:api   (backend chạy ở :8000) → src/lib/api-types.ts
 * Backend đổi schema ⇒ build frontend báo lỗi kiểu ngay (mục 3.3 kế hoạch).
 */
export const API_BASE = "/api/v1";

/** Định dạng lỗi thống nhất của backend (mục 5.4.1). */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

let token: string | null = localStorage.getItem("whybi.token");
export const setToken = (t: string | null) => {
  token = t;
  if (t) localStorage.setItem("whybi.token", t);
  else localStorage.removeItem("whybi.token");
};

/** Thông báo dễ hiểu cho người dùng theo mã lỗi (GD-02 "lỗi API hiện thông báo dễ hiểu"). */
export const FRIENDLY: Record<string, string> = {
  NODE_LOCKED: "Nút này đang khóa – hãy Đạt các nút tiên quyết trước.",
  CYCLE_DETECTED: "Cạnh này tạo chu trình trong cây kỹ năng.",
  INVALID_FILE: "Tệp không hợp lệ (chỉ PDF/DOCX ≤ 20 MB).",
  FORBIDDEN: "Bạn không có quyền xem nội dung này.",
  UNAUTHORIZED: "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.",
  NOT_IMPLEMENTED: "Chức năng đang được phát triển.",
};

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const res = await fetch(API_BASE + path, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const e = body.error ?? {};
    throw new ApiError(res.status, e.code ?? "HTTP_ERROR", FRIENDLY[e.code] ?? e.message ?? res.statusText, e.details);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}
