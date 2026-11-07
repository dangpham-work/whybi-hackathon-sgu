import { API_BASE, ApiError, getToken } from "./api";

/** Tên tệp trong tiêu đề Content-Disposition (`attachment; filename="x.csv"`), không có thì dùng tên dự phòng. */
export function filenameFrom(disposition: string | null, fallback: string): string {
  const m = disposition?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  return m ? decodeURIComponent(m[1]) : fallback;
}

/** Tải một tệp có yêu cầu đăng nhập (báo cáo CSV/PDF): fetch kèm token rồi cho trình duyệt lưu. */
export async function downloadFile(path: string, fallbackName: string): Promise<string> {
  const token = getToken();
  let res: Response;
  try {
    res = await fetch(API_BASE + path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  } catch (e) {
    throw new ApiError(0, "NETWORK_ERROR", e instanceof Error ? e.message : String(e));
  }
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { error?: { code?: string; message?: string } };
    throw new ApiError(res.status, body.error?.code ?? "HTTP_ERROR", body.error?.message);
  }
  const name = filenameFrom(res.headers.get("Content-Disposition"), fallbackName);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return name;
}
