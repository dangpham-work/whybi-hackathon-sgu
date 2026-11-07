/**
 * Lớp gọi API dùng chung (GD-02). Kiểu dữ liệu sinh tự động từ OpenAPI của backend:
 *   npm run gen:api   (backend chạy ở :8000) → src/lib/api-types.ts
 * Backend đổi schema ⇒ build frontend báo lỗi kiểu ngay (mục 3.3 kế hoạch).
 *
 * Dùng:
 *   const cls = await http.get<Schema<"ClassOut">>(`/classes/${id}`);
 *   try { … } catch (e) { toast(errorMessage(e)); }
 */
import type { components } from "./api-types";

export const API_BASE = "/api/v1";

/** Kiểu schema sinh từ OpenAPI, vd. `Schema<"ClassOut">`. */
export type Schema<K extends keyof components["schemas"]> = components["schemas"][K];

/** Định dạng lỗi thống nhất của backend (mục 5.4.1). */
export type ErrorBody = { error?: { code?: string; message?: string; details?: Record<string, unknown> } };

/** Lỗi khi gọi API. `message` luôn là câu dễ hiểu để hiện cho người dùng. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ---- token đăng nhập (localStorage có thể không dùng được: chế độ riêng tư, SSR, test) ----
const TOKEN_KEY = "whybi.token";

function storage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

let token: string | null = storage()?.getItem(TOKEN_KEY) ?? null;

export const getToken = () => token;

export const setToken = (t: string | null) => {
  token = t;
  try {
    if (t) storage()?.setItem(TOKEN_KEY, t);
    else storage()?.removeItem(TOKEN_KEY);
  } catch {
    /* bỏ qua: không lưu được thì vẫn giữ token trong bộ nhớ */
  }
};

/** Sự kiện phát trên window khi backend trả 401 – layout nghe để chuyển về trang đăng nhập. */
export const UNAUTHORIZED_EVENT = "whybi:unauthorized";

/** Thông báo dễ hiểu cho người dùng theo mã lỗi (GD-02 "lỗi API hiện thông báo dễ hiểu"). */
export const FRIENDLY: Record<string, string> = {
  NODE_LOCKED: "Nút này đang khóa – hãy Đạt các nút tiên quyết trước.",
  CYCLE_DETECTED: "Cạnh này tạo chu trình trong cây kỹ năng.",
  INVALID_FILE: "Tệp không hợp lệ (chỉ PDF/DOCX ≤ 20 MB).",
  FORBIDDEN: "Bạn không có quyền xem nội dung này.",
  UNAUTHORIZED: "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.",
  NOT_IMPLEMENTED: "Chức năng đang được phát triển.",
  NOT_FOUND: "Không tìm thấy nội dung yêu cầu.",
  VALIDATION_ERROR: "Dữ liệu nhập chưa hợp lệ, vui lòng kiểm tra lại.",
  RATE_LIMITED: "Bạn thao tác quá nhanh, vui lòng thử lại sau ít phút.",
  SERVER_ERROR: "Máy chủ đang gặp sự cố, vui lòng thử lại sau.",
  NETWORK_ERROR: "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.",
  TIMEOUT: "Máy chủ phản hồi quá lâu, vui lòng thử lại.",
  HTTP_ERROR: "Có lỗi xảy ra, vui lòng thử lại.",
};

/** Mã lỗi suy từ mã HTTP khi backend không trả thân lỗi chuẩn (vd. nginx 502). */
function codeFromStatus(status: number): string {
  if (status === 401) return "UNAUTHORIZED";
  if (status === 403) return "FORBIDDEN";
  if (status === 404) return "NOT_FOUND";
  if (status === 422) return "VALIDATION_ERROR";
  if (status === 429) return "RATE_LIMITED";
  if (status === 501) return "NOT_IMPLEMENTED";
  if (status >= 500) return "SERVER_ERROR";
  return "HTTP_ERROR";
}

/** Câu dễ hiểu từ một lỗi bất kỳ – dùng ở mọi chỗ hiện lỗi cho người dùng. */
export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  return FRIENDLY.HTTP_ERROR;
}

export type ApiInit = Omit<RequestInit, "body"> & {
  /** Đối tượng sẽ được JSON.stringify, hoặc FormData / chuỗi gửi nguyên. */
  body?: unknown;
  /** Hết thời gian chờ (ms). Mặc định 15 giây; 0 = không giới hạn. */
  timeoutMs?: number;
};

const DEFAULT_TIMEOUT = 15_000;

function encodeBody(body: unknown, headers: Headers): BodyInit | undefined {
  if (body === undefined || body === null) return undefined;
  if (body instanceof FormData || body instanceof Blob || typeof body === "string") return body;
  headers.set("Content-Type", "application/json");
  return JSON.stringify(body);
}

async function readError(res: Response): Promise<ApiError> {
  const body = (await res.json().catch(() => ({}))) as ErrorBody;
  const e = body?.error ?? {};
  const code = e.code ?? codeFromStatus(res.status);
  const message = FRIENDLY[code] ?? e.message ?? FRIENDLY[codeFromStatus(res.status)];
  return new ApiError(res.status, code, message, e.details ?? {});
}

export async function api<T>(path: string, init: ApiInit = {}): Promise<T> {
  const { body, timeoutMs = DEFAULT_TIMEOUT, signal: outer, ...rest } = init;
  const headers = new Headers(rest.headers);
  headers.set("Accept", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const ctrl = new AbortController();
  let timedOut = false;
  const timer = timeoutMs > 0 ? setTimeout(() => ((timedOut = true), ctrl.abort()), timeoutMs) : undefined;
  const onOuterAbort = () => ctrl.abort();
  if (outer?.aborted) ctrl.abort();
  outer?.addEventListener("abort", onOuterAbort);

  let res: Response;
  try {
    res = await fetch(API_BASE + path, { ...rest, headers, body: encodeBody(body, headers), signal: ctrl.signal });
  } catch (err) {
    // Bên gọi tự hủy (rời trang) – ném lại nguyên lỗi để hook bỏ qua.
    if (outer?.aborted) throw err;
    throw timedOut ? new ApiError(0, "TIMEOUT", FRIENDLY.TIMEOUT) : new ApiError(0, "NETWORK_ERROR", FRIENDLY.NETWORK_ERROR);
  } finally {
    clearTimeout(timer);
    outer?.removeEventListener("abort", onOuterAbort);
  }

  if (!res.ok) {
    const err = await readError(res);
    if (res.status === 401) {
      setToken(null);
      if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
    }
    throw err;
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

/** Viết tắt theo phương thức HTTP. */
export const http = {
  get: <T>(path: string, init?: ApiInit) => api<T>(path, { ...init, method: "GET" }),
  post: <T>(path: string, body?: unknown, init?: ApiInit) => api<T>(path, { ...init, method: "POST", body }),
  put: <T>(path: string, body?: unknown, init?: ApiInit) => api<T>(path, { ...init, method: "PUT", body }),
  patch: <T>(path: string, body?: unknown, init?: ApiInit) => api<T>(path, { ...init, method: "PATCH", body }),
  del: <T = void>(path: string, init?: ApiInit) => api<T>(path, { ...init, method: "DELETE" }),
};

/** Lỗi do bên gọi tự hủy (AbortController) – không cần hiện cho người dùng. */
export const isAbort = (e: unknown) =>
  typeof e === "object" && e !== null && (e as { name?: unknown }).name === "AbortError";
