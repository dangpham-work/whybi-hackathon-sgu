/**
 * Lớp gọi API dùng chung (GD-02). Kiểu dữ liệu sinh tự động từ OpenAPI của backend:
 *   npm run gen:api   (backend chạy ở :8000) → src/lib/api-types.ts
 * Backend đổi schema ⇒ build frontend báo lỗi kiểu ngay (mục 3.3 kế hoạch).
 *
 * Dùng:
 *   const tree = await apiCall("get", "/classes/{class_id}/tree", { path: { class_id } });   // kiểu TreeVersion
 *   const s = await apiCall("post", "/sessions", { body: { nodeId, inputMode: "TEXT", ttsEnabled: false } });
 * Trong component: useApi() (lib/useApi.ts) + <AsyncView> (components/AsyncView.tsx) lo trạng thái tải / lỗi.
 */
import type { components, paths } from "./api-types";

export const API_BASE = "/api/v1";

export type Schemas = components["schemas"];
/** Kiểu một schema backend, vd. Schema<"TreeVersion">, Schema<"SessionResult">. */
export type Schema<K extends keyof Schemas> = Schemas[K];

// ---------------------------------------------------------------- lỗi

/** Thông báo dễ hiểu cho người dùng theo mã lỗi (GD-02 "lỗi API hiện thông báo dễ hiểu"). */
export const FRIENDLY: Record<string, string> = {
  NODE_LOCKED: "Nút này đang khóa – hãy Đạt các nút tiên quyết trước.",
  CYCLE_DETECTED: "Cạnh này tạo chu trình trong cây kỹ năng.",
  INVALID_FILE: "Tệp không hợp lệ (chỉ PDF/DOCX ≤ 20 MB).",
  FORBIDDEN: "Bạn không có quyền xem nội dung này.",
  UNAUTHORIZED: "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.",
  NOT_IMPLEMENTED: "Chức năng đang được phát triển.",
  CLASS_NOT_FOUND: "Không tìm thấy lớp học (có thể đã bị xóa hoặc bạn chưa tham gia).",
  COURSE_NOT_FOUND: "Không tìm thấy môn học, vui lòng kiểm tra lại mã môn học.",
  LECTURER_PROFILE_MISSING: "Tài khoản của bạn chưa có hồ sơ giảng viên.",
  NOT_FOUND: "Không tìm thấy nội dung bạn cần.",
  VALIDATION_ERROR: "Dữ liệu gửi lên chưa hợp lệ, vui lòng kiểm tra lại.",
  RATE_LIMITED: "Bạn thao tác quá nhanh, chờ một chút rồi thử lại.",
  QUOTA_EXCEEDED: "Bạn đã dùng hết lượt hôm nay. Hãy quay lại vào ngày mai.",
  NETWORK_ERROR: "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.",
  // Bản đồ học tập & bắt đầu phiên – C2-10 (backend/app/models/schemas/mastery.py, api/trees.py)
  NOT_ENROLLED: "Bạn chưa tham gia lớp này. Nhập mã lớp ở danh sách lớp để tham gia.",
  TREE_NOT_PUBLISHED: "Giảng viên chưa phát hành cây kỹ năng cho lớp này. Hãy quay lại sau.",
  NODE_NOT_FOUND: "Không tìm thấy nút kỹ năng này (cây có thể vừa được cập nhật).",
  RETRY_COOLDOWN: "Bạn vừa giảng nút này. Nghỉ một chút rồi thử lại sau ít phút.",
  NODE_ALREADY_MASTERED: "Bạn đã Đạt nút này rồi – hãy chọn nút khác để học tiếp.",
  SESSION_IN_PROGRESS: "Bạn đang có một phiên giảng chưa xong ở nút này.",
  // Phiên giảng lại (C1-07, GD-07)
  SESSION_NOT_FOUND: "Không tìm thấy phiên giảng này.",
  SESSION_NOT_ACTIVE: "Phiên này đã kết thúc – bạn không gửi thêm được. Hãy xem kết quả hoặc bắt đầu phiên mới.",
  RESULT_NOT_READY: "Whybi vẫn đang chấm lời giảng của bạn, vui lòng chờ một chút.",
  TOKEN_BUDGET_EXCEEDED: "Phiên đã dùng hết lượt trao đổi với Whybi. Hãy bắt đầu phiên mới.",
  // Ghi âm / chép lời – POST /sessions/{id}/audio (C1-12, backend services/speech.py); Bảng 7.4: luôn gợi ý gõ chữ (#154)
  NO_SPEECH_DETECTED: "Whybi chưa nghe rõ lời bạn. Hãy ghi lại gần micro hơn, hoặc gõ chữ.",
  EMPTY_AUDIO: "Bản ghi trống – chưa có tiếng nào. Hãy ghi lại, hoặc gõ chữ.",
  STT_UNAVAILABLE: "Whybi tạm thời không nghe được giọng nói. Hãy gõ chữ để giảng tiếp, hoặc ghi lại sau ít phút.",
  UNSUPPORTED_AUDIO_FORMAT: "Trình duyệt ghi âm theo định dạng Whybi chưa đọc được. Hãy gõ chữ, hoặc thử trình duyệt khác.",
  AUDIO_TOO_LONG: "Bản ghi dài quá 3 phút. Hãy chia nhỏ lời giảng rồi ghi lại, hoặc gõ chữ.",
  AUDIO_TOO_LARGE: "Tệp ghi âm quá lớn. Hãy ghi ngắn hơn, hoặc gõ chữ.",
  AUDIO_STORE_UNAVAILABLE: "Chưa lưu được bản ghi. Hãy ghi lại sau ít phút, hoặc gõ chữ để giảng tiếp.",
  LLM_UNAVAILABLE: "Whybi đang tạm nghỉ một chút. Lời giảng của bạn vẫn còn – hãy gửi lại sau ít phút.",
  NO_SOURCE_MATERIAL: "Lớp chưa có giáo trình đã xử lý – hãy tải giáo trình lên trước rồi thử lại.",
};

const BY_STATUS: [test: (s: number) => boolean, text: string][] = [
  [(s) => s === 401, FRIENDLY.UNAUTHORIZED],
  [(s) => s === 403, FRIENDLY.FORBIDDEN],
  [(s) => s === 404, FRIENDLY.NOT_FOUND],
  [(s) => s === 422, FRIENDLY.VALIDATION_ERROR],
  [(s) => s === 429, FRIENDLY.RATE_LIMITED],
  [(s) => s >= 500, "Máy chủ đang bận hoặc gặp sự cố. Vui lòng thử lại sau ít phút."],
];
export const GENERIC_ERROR = "Có lỗi xảy ra, vui lòng thử lại.";

/**
 * Câu hiển thị cho người dùng: theo mã lỗi → theo mã HTTP → câu chung.
 * Không bao giờ hiện thẳng `message` của máy chủ (có thể là tiếng Anh / chi tiết kỹ thuật) – giữ ở `serverMessage`.
 */
export function friendlyMessage(status: number, code: string, details: Record<string, unknown> = {}): string {
  if (code === "NOT_IMPLEMENTED" && typeof details.card === "string") return `Chức năng đang được phát triển (thẻ ${details.card}).`;
  return FRIENDLY[code] ?? BY_STATUS.find(([t]) => t(status))?.[1] ?? GENERIC_ERROR;
}

/** Định dạng lỗi thống nhất của backend (mục 5.4.1): { error: { code, message, details } }. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public serverMessage?: string,
    public details: Record<string, unknown> = {},
  ) {
    super(friendlyMessage(status, code, details));
    this.name = "ApiError";
  }
  /** Endpoint trả 501 – màn hiện "đang phát triển", không giả lập ngầm (frontend/AGENTS.md). */
  get notImplemented() {
    return this.status === 501 || this.code === "NOT_IMPLEMENTED";
  }
}

/** Câu dễ hiểu cho mọi loại lỗi (ApiError hoặc lỗi lạ). */
export const errorText = (e: unknown) => (e instanceof ApiError ? e.message : GENERIC_ERROR);

// ---------------------------------------------------------------- token

const TOKEN_KEY = "whybi.token";
const storage = {
  get: () => {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set: (t: string | null) => {
    try {
      if (t) localStorage.setItem(TOKEN_KEY, t);
      else localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* trình duyệt chặn lưu trữ – giữ token trong bộ nhớ */
    }
  },
};

/**
 * Token tạm khi chưa có đăng nhập thật (C2-07): đặt VITE_DEV_TOKEN=dev-lecturer | dev-student | dev-admin
 * trong frontend/.env.local. Chỉ dùng ở `npm run dev`; bản build không bao giờ nhận.
 */
const DEV_TOKEN = import.meta.env.DEV ? (import.meta.env.VITE_DEV_TOKEN ?? null) : null;

let token: string | null = storage.get() ?? DEV_TOKEN;
export const getToken = () => token;
export const setToken = (t: string | null) => {
  token = t;
  storage.set(t);
};

// ---------------------------------------------------------------- gọi cấp thấp

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");

  let res: Response;
  try {
    res = await fetch(API_BASE + path, { ...init, headers });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(0, "NETWORK_ERROR", e instanceof Error ? e.message : String(e));
  }

  const text = res.status === 204 ? "" : await res.text();
  let body: unknown;
  try {
    body = text ? JSON.parse(text) : undefined;
  } catch {
    body = undefined; // thân không phải JSON (vd. trang lỗi của nginx)
  }

  if (!res.ok) {
    const e = (body as { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | undefined)?.error ?? {};
    throw new ApiError(res.status, e.code ?? "HTTP_ERROR", e.message ?? res.statusText, e.details ?? {});
  }
  return body as T;
}

// ---------------------------------------------------------------- gọi có kiểu theo OpenAPI

type Method = "get" | "post" | "put" | "patch" | "delete";
type Prefix = "/api/v1";
type FullPath = Extract<keyof paths, `${Prefix}/${string}`>;
type Op<M extends Method, P extends string> = NonNullable<paths[Extract<FullPath, `${Prefix}${P}`>][M]>;

/** Đường dẫn (bỏ /api/v1) có phương thức M, vd. ApiPath<"get"> gồm "/classes/{class_id}/tree". */
export type ApiPath<M extends Method> = {
  [K in FullPath]: [paths[K][M]] extends [undefined] ? never : K extends `${Prefix}${infer R}` ? R : never;
}[FullPath];

type Content<X> = X extends { content: infer C } ? C : never;
type JsonOf<X> = Content<X> extends { "application/json": infer J } ? J : void;
/** Kiểu dữ liệu trả về khi thành công (200 / 201; 204 → void). */
export type ApiResponse<M extends Method, P extends ApiPath<M>> =
  Op<M, P> extends { responses: infer R } ? (R extends { 200: infer X } ? JsonOf<X> : R extends { 201: infer X } ? JsonOf<X> : void) : never;

type BodyOf<O> = O extends { requestBody: infer B }
  ? Content<B> extends { "application/json": infer J }
    ? { body: J }
    : Content<B> extends { "multipart/form-data": unknown }
      ? { body: FormData }
      : { body?: never }
  : O extends { requestBody?: infer B }
    ? [B] extends [undefined]
      ? { body?: never }
      : Content<NonNullable<B>> extends { "application/json": infer J }
        ? { body?: J }
        : { body?: never }
    : { body?: never };
type PathParams<O> = O extends { parameters: { path: infer P } } ? ([P] extends [undefined] ? { path?: never } : { path: P }) : { path?: never };
type QueryParams<O> = O extends { parameters: { query?: infer Q } } ? ([NonNullable<Q>] extends [never] ? { query?: never } : { query?: Q }) : { query?: never };

export type ApiOptions<M extends Method, P extends ApiPath<M>> = PathParams<Op<M, P>> &
  QueryParams<Op<M, P>> &
  BodyOf<Op<M, P>> & { signal?: AbortSignal; headers?: HeadersInit };

type OptArgs<M extends Method, P extends ApiPath<M>> = {} extends ApiOptions<M, P> ? [opts?: ApiOptions<M, P>] : [opts: ApiOptions<M, P>];

/** Ghép "/classes/{class_id}/tree" + { class_id } + query → URL. */
export function buildPath(template: string, path?: Record<string, unknown>, query?: Record<string, unknown>): string {
  const url = template.replace(/\{(\w+)\}/g, (_, k: string) => {
    const v = path?.[k];
    if (v === undefined || v === null) throw new Error(`Thiếu tham số đường dẫn "${k}" cho ${template}`);
    return encodeURIComponent(String(v));
  });
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v === undefined || v === null) continue;
    for (const item of Array.isArray(v) ? v : [v]) qs.append(k, String(item));
  }
  const s = qs.toString();
  return s ? `${url}?${s}` : url;
}

type RawOptions = { path?: Record<string, unknown>; query?: Record<string, unknown>; body?: unknown; signal?: AbortSignal; headers?: HeadersInit };

/** Gọi một endpoint trong OpenAPI với kiểu đầy đủ cho tham số, body và kết quả. */
export function apiCall<M extends Method, P extends ApiPath<M>>(method: M, path: P, ...args: OptArgs<M, P>): Promise<ApiResponse<M, P>> {
  // Kiểu đã được kiểm ở chữ ký; bên trong chỉ cần dạng chung (tránh TS tính lại union lớn).
  const o: RawOptions = ((args as unknown[])[0] ?? {}) as RawOptions;
  const body = o.body === undefined ? undefined : o.body instanceof FormData ? o.body : JSON.stringify(o.body);
  return api<ApiResponse<M, P>>(buildPath(path, o.path, o.query), { method: method.toUpperCase(), body, signal: o.signal, headers: o.headers });
}
