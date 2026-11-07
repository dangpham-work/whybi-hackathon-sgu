// KT-13 – kiểm thử tải phiên giảng (Bảng 7.3: 20 / 50 / 100 phiên đồng thời, p95 ≤ 5 s).
// Chạy: k6 run -e BASE=http://localhost -e VUS=20 evals/perf/k6-sessions.js   (backend nên để LLM_MODE=fake)
import http from "k6/http";
import { check, sleep } from "k6";

const BASE = __ENV.BASE || "http://localhost";
export const options = {
  vus: Number(__ENV.VUS || 20),
  duration: __ENV.DURATION || "2m",
  thresholds: { http_req_duration: ["p(95)<5000"], http_req_failed: ["rate<0.01"] },
};

export function setup() {
  // TODO KT-13: đăng nhập 30 SV mẫu (seed/users.json) → trả danh sách token.
  return { tokens: [] };
}

export default function (data) {
  const token = data.tokens[__VU % Math.max(data.tokens.length, 1)];
  const headers = { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) };
  const res = http.get(`${BASE}/health`, { headers });
  check(res, { "200": (r) => r.status === 200 });
  // TODO KT-13: POST /api/v1/sessions → các lượt /turns → /complete theo hợp đồng schemas/session.py
  sleep(1);
}
