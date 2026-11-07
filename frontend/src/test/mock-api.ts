/**
 * Giả lập backend trong test bằng cách thay `fetch`: mockApi({ "POST /auth/login": ok({...}) }).
 * Khóa là "METHOD /đường-dẫn" (bỏ /api/v1 và query). Gọi tới route chưa khai báo → 501 NOT_IMPLEMENTED như backend scaffold.
 */
type Reply = Response | ((req: { url: string; init: RequestInit; body: unknown }) => Response);

export const ok = (body: unknown, status = 200) =>
  new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
export const err = (status: number, code: string, message = code, details: Record<string, unknown> = {}) =>
  ok({ error: { code, message, details } }, status);

export function mockApi(routes: Record<string, Reply>) {
  const calls: { key: string; url: string; init: RequestInit; body: unknown }[] = [];
  const fetchMock = vi.fn(async (input: string, init: RequestInit = {}) => {
    const url = String(input);
    const method = (init.method ?? "GET").toUpperCase();
    const key = `${method} ${url.replace(/^\/api\/v1/, "").split("?")[0]}`;
    const body = typeof init.body === "string" ? JSON.parse(init.body) : init.body;
    calls.push({ key, url, init, body });
    const reply = routes[key];
    if (!reply) return err(501, "NOT_IMPLEMENTED", "chưa khai báo trong test", { card: "TEST" });
    return typeof reply === "function" ? reply({ url, init, body }) : reply.clone();
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, called: (key: string) => calls.filter((c) => c.key === key) };
}
