import { apiCall, type Schema } from "./api";
import { useApi } from "./useApi";

export type ClassOut = Schema<"ClassOut">;

/** Danh sách lớp của GV (GV-01); GV-02/03 tìm lớp theo id trong danh sách này vì chưa có GET /classes/{id}. */
export const useMyClasses = () => useApi((signal) => apiCall("get", "/classes", { signal }), []);

/** Chép mã tham gia; trình duyệt chặn clipboard thì trả false để màn báo cho GV tự chép. */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
