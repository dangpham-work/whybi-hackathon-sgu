import { API_BASE, ApiError, getToken } from "./api";

/**
 * Tải ghi âm một lượt thành URL tạm cho <audio>. `<audio src>` không gửi được tiêu đề Authorization nên phải tải bằng fetch.
 * 404 AUDIO_NOT_AVAILABLE = SV không đồng ý lưu hoặc đã quá hạn lưu (BR-13).
 */
export async function fetchAudioUrl(audioUrl: string): Promise<string> {
  const path = audioUrl.startsWith(API_BASE) ? audioUrl : API_BASE + audioUrl;
  const token = getToken();
  let res: Response;
  try {
    res = await fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  } catch (e) {
    throw new ApiError(0, "NETWORK_ERROR", e instanceof Error ? e.message : String(e));
  }
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { error?: { code?: string; message?: string } };
    throw new ApiError(res.status, body.error?.code ?? "HTTP_ERROR", body.error?.message);
  }
  return URL.createObjectURL(await res.blob());
}
