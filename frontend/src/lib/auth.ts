/**
 * Phiên đăng nhập phía trình duyệt (GD-04, FR-AD-01). Hợp đồng theo scaffold `backend/app/api/auth.py` (C2-07 – Long):
 *   POST /auth/login {email, password} → TokenPair {accessToken, refreshToken, tokenType, expiresIn}
 *   GET  /me → Me {id, fullName, email, role, avatarUrl?}   · POST /auth/logout (204)
 *   POST /auth/forgot-password {email} (202)
 * GIẢ ĐỊNH về C2-07 (ghi trong PR GD-04): accessToken dùng làm Bearer; vai trò lấy từ GET /me (không giải mã JWT ở client);
 * sai email / mật khẩu trả 401; chưa tự gọi /auth/refresh khi token hết hạn (30 phút – NFR-07) → làm khi C2-07 chốt.
 */
import { useEffect, useSyncExternalStore } from "react";
import { apiCall, getToken, setToken, type Schema } from "./api";

export type Me = Schema<"Me">;
export type Role = Schema<"Role">;

export const ROLE_LABEL: Record<Role, string> = { LECTURER: "Giảng viên", STUDENT: "Sinh viên", ADMIN: "Quản trị viên" };

/** Màn đầu tiên theo vai (sơ đồ 5.5.1: Đăng nhập → GV-01 / SV-01; QTV → AD-01). */
export const homeFor = (role: Role) => ({ LECTURER: "/gv/classes", STUDENT: "/sv/classes", ADMIN: "/admin/users" })[role];

/** "Trần Bảo Châu" → "Bảo Châu"; "TS. Nguyễn Văn Bình" → "Văn Bình" (lời chào SV-01). */
export const givenName = (fullName: string) => {
  const words = fullName.replace(/^(TS|ThS|PGS|GS)\.\s*/u, "").split(/\s+/).filter(Boolean);
  return words.length > 1 ? words.slice(1).join(" ") : (words[0] ?? "");
};

let user: Me | null = null;
let loading: Promise<Me | null> | null = null;
let generation = 0;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());
const setUser = (u: Me | null) => {
  user = u;
  notify();
};

/**
 * Refresh token CHỈ giữ trong bộ nhớ (không localStorage – tránh XSS chiếm phiên lâu dài).
 * Chờ C2-07 chốt: tốt nhất backend đặt cookie httpOnly cho refresh, client chỉ gọi POST /auth/refresh.
 */
let refreshToken: string | null = null;
const storeRefresh = (t: string | null) => {
  refreshToken = t;
};
export const hasRefreshToken = () => refreshToken !== null;

/** `?next=` sau đăng nhập: chỉ nhận đường dẫn cùng gốc ("/…"), chặn "//x", "/\x", "https://…", "javascript:…". */
export function safeNext(next: string | null): string | null {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return null;
  try {
    const url = new URL(next, location.origin);
    return url.origin === location.origin ? url.pathname + url.search + url.hash : null;
  } catch {
    return null;
  }
}

export const auth = {
  get user() {
    return user;
  },

  /** Đăng nhập rồi nạp hồ sơ; ném ApiError nếu lỗi (trang tự đổi câu cho 401). */
  async login(email: string, password: string): Promise<Me> {
    const current = ++generation;
    loading = null;
    setToken(null);
    storeRefresh(null);
    setUser(null);
    try {
      const tokens = await apiCall("post", "/auth/login", { body: { email, password } });
      if (current !== generation) throw new DOMException("Phiên đã thay đổi", "AbortError");
      setToken(tokens.accessToken);
      storeRefresh(tokens.refreshToken);
      const me = await apiCall("get", "/me");
      if (current !== generation) throw new DOMException("Phiên đã thay đổi", "AbortError");
      setUser(me);
      return me;
    } catch (e) {
      if (current === generation) {
        setToken(null);
        storeRefresh(null);
      }
      throw e;
    }
  },

  /** Nạp hồ sơ một lần nếu đã có token (sau khi tải lại trang). Lỗi → null, không ném. */
  ensureUser(): Promise<Me | null> {
    if (user) return Promise.resolve(user);
    if (!getToken()) return Promise.resolve(null);
    if (loading) return loading;
    const current = generation;
    const token = getToken();
    const request = apiCall("get", "/me")
      .then((me) => {
        if (current !== generation || getToken() !== token) return null;
        setUser(me);
        return me;
      })
      .catch(() => null)
      .finally(() => { if (loading === request) loading = null; });
    loading = request;
    return request;
  },

  /** Đăng xuất: luôn xóa phiên phía trình duyệt, kể cả khi máy chủ lỗi. */
  async logout(): Promise<void> {
    ++generation;
    loading = null;
    const request = getToken() ? apiCall("post", "/auth/logout", { body: { refreshToken } }) : Promise.resolve();
    setToken(null);
    storeRefresh(null);
    setUser(null);
    try {
      await request;
    } catch {
      /* phiên phía máy chủ sẽ tự hết hạn */
    }
  },

  subscribe(l: () => void) {
    listeners.add(l);
    return () => listeners.delete(l);
  },

  /** Chỉ dùng trong test. */
  reset() {
    ++generation;
    loading = null;
    setToken(null);
    storeRefresh(null);
    setUser(null);
  },
};

/** Người dùng hiện tại; tự nạp /me nếu đã có token mà chưa có hồ sơ. */
export function useCurrentUser(): Me | null {
  const u = useSyncExternalStore(auth.subscribe, () => auth.user);
  useEffect(() => {
    if (!u) void auth.ensureUser();
  }, [u]);
  return u;
}
