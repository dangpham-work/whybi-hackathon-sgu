import { expect, test, type APIRequestContext, type APIResponse, type Page, type Response } from "@playwright/test";
import { execFile } from "node:child_process";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import type { components } from "../../frontend/src/lib/api-types";

// KT-11 (#50): UI + nginx/API/events/Redis/Celery thật, LLM fake. Không mock HTTP/WS.
// Fixture UI rút còn hai nút gốc; ví dụ đầy đủ 6.6.4 kiểm riêng ở backend.
type Schema<K extends keyof components["schemas"]> = components["schemas"][K];
type Actor = { headers: { Authorization: string }; token: string; id: string; fullName: string };
type Message = { channel: string; event: string; payload: Record<string, unknown> };
const run = promisify(execFile);
const root = fileURLToPath(new URL("../../", import.meta.url));
const compose = ["compose", "-p", process.env.KT06_COMPOSE_PROJECT ?? "whybi"];
const options = { cwd: root, timeout: 90_000, maxBuffer: 1024 * 1024 };
const password = "Whybi@2026"; // Mật khẩu công khai của seed/users.json.
const explanation = "Con trỏ lưu địa chỉ của biến. Toán tử & lấy địa chỉ, còn * truy cập giá trị tại địa chỉ đó.";
const answer = "Con tro luu dia chi. Kieu du lieu quyet dinh cach truy cap vung nho.";
let courseId: string;

async function json<T>(response: APIResponse | Response): Promise<T> {
  expect(response.ok(), `${response.status()} ${await response.text()}`).toBeTruthy();
  return response.json() as Promise<T>;
}

test.beforeAll(async ({ request, baseURL }) => {
  test.setTimeout(120_000);
  const health = await json<{ env: string; llm_mode: string }>(await request.get("/health"));
  expect(health.llm_mode).toBe("fake");
  expect(["dev", "test"]).toContain(health.env);
  // MX4 đọc enrollmentId ở DB local vì API chưa trả cho SV; luôn kiểm đúng stack.
  const url = new URL(baseURL!);
  expect(["localhost", "127.0.0.1", "[::1]"]).toContain(url.hostname);
  const port = await run("docker", [...compose, "port", "nginx", "80"], options);
  const expected = url.port || (url.protocol === "https:" ? "443" : "80");
  expect(port.stdout.trim().split(/\r?\n/).some(line => line.endsWith(`:${expected}`)),
    "KT06_COMPOSE_PROJECT/COMPOSE_FILE phải trỏ đúng stack E2E_BASE_URL").toBeTruthy();
  if (process.env.KT06_COURSE_ID) courseId = process.env.KT06_COURSE_ID;
  else {
    const prepared = await run("docker", [...compose, "run", "--rm", "--no-deps", "-T",
      "-e", "PYTHONPATH=/app", "-v", `${root}scripts:/workspace/scripts:ro`,
      "-v", `${root}seed:/workspace/seed:ro`, "api", "python", "/workspace/scripts/prepare_kt06.py"], options);
    courseId = JSON.parse(prepared.stdout).courseId;
  }
  expect(courseId).toMatch(/^[0-9a-f]{8}-[0-9a-f-]{27}$/i);
});

async function login(request: APIRequestContext, email: string): Promise<Actor> {
  const auth = await json<{ accessToken: string }>(await request.post("/api/v1/auth/login", { data: { email, password } }));
  const headers = { Authorization: `Bearer ${auth.accessToken}` };
  const me = await json<{ id: string; fullName: string }>(await request.get("/api/v1/me", { headers }));
  return { headers, token: auth.accessToken, ...me };
}

async function openAs(page: Page, actor: Actor, path: string) {
  await page.addInitScript(token => localStorage.setItem("whybi.token", token), actor.token);
  await page.goto(path);
}

async function prepare(request: APIRequestContext, threshold = 70, twoNodes = false) {
  const teacher = await login(request, "gv@whybi.test");
  const students = await Promise.all(["sv01@whybi.test", "sv02@whybi.test"].map(email => login(request, email)));
  const cls = await json<{ id: string; joinCode: string }>(await request.post("/api/v1/classes", {
    headers: teacher.headers, data: { courseId, name: `KT-11 ${randomUUID()}`, semester: "KT11-local" },
  }));
  await json(await request.put(`/api/v1/classes/${cls.id}/settings`, {
    headers: teacher.headers,
    data: { passThreshold: threshold, greenThreshold: 0.7, yellowThreshold: 0.4, minSample: 1, challengeCount: 3 },
  }));
  const rubric = {
    keyPoints: ["Con trỏ lưu địa chỉ", "Lấy địa chỉ và giải tham chiếu", "Vòng đời của vùng nhớ"]
      .map((content, i) => ({ id: `KP${i + 1}`, content, isRequired: true })),
    sourcePages: [45, 46], approved: true,
  };
  const nodes = [{ key: "pointer", code: "N5", title: "Con trỏ", rubric }];
  if (twoNodes) nodes.push({ key: "recursion", code: "N4", title: "Đệ quy", rubric });
  const tree = await json<Schema<"TreeVersion">>(await request.post(`/api/v1/classes/${cls.id}/tree-versions`, {
    headers: teacher.headers, data: { nodes, edges: [] },
  }));
  for (const node of tree.nodes) {
    await json(await request.put(`/api/v1/nodes/${node.id}/rubric`, { headers: teacher.headers, data: rubric }));
  }
  await json(await request.post(`/api/v1/tree-versions/${tree.id}/publish`, { headers: teacher.headers }));
  for (const student of twoNodes ? students : students.slice(0, 1)) {
    await json(await request.post("/api/v1/classes/join", { headers: student.headers, data: { joinCode: cls.joinCode } }));
  }
  return { classId: cls.id, teacher, students, nodes: tree.nodes };
}

async function finishApi(request: APIRequestContext, student: Actor, nodeId: string) {
  const created = await json<Schema<"SessionCreated">>(await request.post("/api/v1/sessions", {
    headers: student.headers, data: { nodeId, inputMode: "TEXT", ttsEnabled: false },
  }));
  let reply = await json<Schema<"TurnReply">>(await request.post(`/api/v1/sessions/${created.sessionId}/turns`, {
    headers: student.headers, data: { turnType: "EXPLANATION", text: explanation },
  }));
  let lastSentAt = 0;
  for (let i = 0; reply.status === "CHALLENGING" && i < 5; i++) {
    // Đo TRƯỚC request cuối, không lấy sau response rồi ép số âm về 0.
    lastSentAt = performance.now();
    reply = await json(await request.post(`/api/v1/sessions/${created.sessionId}/turns`, {
      headers: student.headers, data: { turnType: "ANSWER", text: answer },
    }));
  }
  expect(reply.status).toBe("COMPLETED");
  expect(lastSentAt).toBeGreaterThan(0);
  return { sessionId: created.sessionId, lastSentAt };
}

for (const [threshold, color, label, state] of [
  [70, "GREEN", "Đạt ≥ 70%", "Đạt"], [90, "RED", "< 40%", "Chưa đạt"],
] as const) {
  test(`MX3 (4:30–5:45): UI XÁM → ${color}, WS/cây/lưới/chi tiết, ≤ 3 giây`, async ({ page, request }, info) => {
    const f = await prepare(request, threshold);
    const nodeId = f.nodes[0].id!;
    const inbox: { at: number; msg: Message }[] = [];
    page.on("websocket", ws => ws.on("framereceived", frame => {
      inbox.push({ at: performance.now(), msg: JSON.parse(frame.payload.toString()) as Message });
    }));
    await openAs(page, f.teacher, `/gv/classes/${f.classId}/heatmap`);
    await expect(page.getByLabel("N5 Con trỏ – Chưa đủ mẫu", { exact: true })).toBeVisible();
    await expect.poll(() => inbox.some(m => m.msg.event === "subscribed"
      && m.msg.channel === `class:${f.classId}:heatmap`)).toBeTruthy();
    const completed = await finishApi(request, f.students[0], nodeId);
    const visible = page.getByLabel(`N5 Con trỏ – ${label}`, { exact: true });
    await expect(visible).toBeVisible({ timeout: 15_000 });
    const uiLatencyMs = performance.now() - completed.lastSentAt;
    await expect(visible).toContainText(`${color === "GREEN" ? 100 : 0}% Đạt · 1 đã thử`);
    const finalState = color === "GREEN" ? "MASTERED" : "NOT_PASSED";
    await expect.poll(() => inbox.some(m => m.msg.event === "heatmap.cell" && m.msg.payload.nodeId === nodeId
      && m.msg.payload.studentId === f.students[0].id && m.msg.payload.state === finalState)).toBeTruthy();
    const cell = inbox.find(m => m.msg.event === "heatmap.cell" && m.msg.payload.nodeId === nodeId
      && m.msg.payload.studentId === f.students[0].id && m.msg.payload.state === finalState);
    const node = inbox.find(m => m.msg.event === "heatmap.node" && m.msg.payload.nodeId === nodeId && m.msg.payload.color === color);
    expect(cell?.msg.payload.state).toBe(color === "GREEN" ? "MASTERED" : "NOT_PASSED");
    expect(node?.msg.payload.attemptedCount).toBe(1);
    await info.attach("latency.json", { body: JSON.stringify({ classId: f.classId, sessionId: completed.sessionId,
      scope: "local fake; before final ANSWER HTTP request -> visible GV05 node; minSample=1",
      uiLatencyMs: Math.round(uiLatencyMs),
      messages: inbox.map(m => ({ afterFinalSendMs: Math.round(m.at - completed.lastSentAt), ...m.msg })) }, null, 2),
      contentType: "application/json" });
    if (color === "RED") {
      await expect(page.getByRole("complementary", { name: "Cảnh báo điểm nghẽn" })).toContainText("Nên giảng lại N5 Con trỏ");
    }
    const snapshot = await json<Schema<"HeatmapSnapshot">>(await request.get(`/api/v1/classes/${f.classId}/heatmap`, { headers: f.teacher.headers }));
    expect(snapshot.nodes.find(n => n.nodeId === nodeId)).toMatchObject({ color, attemptedCount: 1, passedCount: color === "GREEN" ? 1 : 0 });
    await info.attach("heatmap.png", { body: await page.screenshot(), contentType: "image/png" });
    await page.getByRole("tab", { name: "Lưới SV × Nút" }).click();
    const grid = page.getByRole("table", { name: "Lưới sinh viên theo nút" });
    await expect(grid).toContainText(f.students[0].fullName);
    await expect(grid.getByLabel(state, { exact: true })).toBeVisible();
    await page.getByRole("tab", { name: "Chế độ cây" }).click();
    await visible.click();
    await expect(page.getByRole("heading", { name: "N5 – Con trỏ", exact: true })).toBeVisible();
    await expect(page.getByRole("region", { name: "Sinh viên theo trạng thái" })).toContainText(f.students[0].fullName);
    if (color === "RED") await expect(page.getByRole("region", { name: "Truy vết điểm nghẽn gốc" })).toContainText("Nên giảng lại N5 Con trỏ");
    expect(uiLatencyMs, "NFR-03: request cuối → nút UI hiển thị đúng").toBeLessThanOrEqual(3_000);
  });
}

// Chỉ SELECT id của fixture; opt-in và mastery đều ghi qua API thật.
// Không tính bước chuẩn bị này là nghiệm thu công tắc FR-PM-01.
async function optIn(request: APIRequestContext, classId: string, students: Actor[]) {
  expect(classId).toMatch(/^[0-9a-f]{8}-[0-9a-f-]{27}$/i);
  const rows = await run("docker", [...compose, "exec", "-T", "postgres", "psql", "-U", "whybi", "-d", "whybi", "-tA", "-c",
    `SELECT student_id, id FROM enrollments WHERE class_id = '${classId}'`], options);
  const ids = new Map(rows.stdout.trim().split(/\r?\n/).map(line => line.split("|") as [string, string]));
  for (const student of students) {
    expect(ids.has(student.id)).toBeTruthy();
    await json(await request.put(`/api/v1/enrollments/${ids.get(student.id)}/peer-opt-in`, {
      headers: student.headers, data: { peerOptIn: true },
    }));
  }
}

async function preparePair(page: Page, request: APIRequestContext) {
  const f = await prepare(request, 70, true);
  for (const [index, key] of ["pointer", "recursion"].entries()) {
    await finishApi(request, f.students[index], f.nodes.find(n => n.key === key)!.id!);
    await expect.poll(async () => {
      const map = await json<Schema<"MyMap">>(await request.get(`/api/v1/classes/${f.classId}/my-map`, { headers: f.students[index].headers }));
      return map.progress.find(p => p.nodeKey === key)?.state;
    }, { timeout: 15_000 }).toBe("MASTERED");
  }
  await optIn(request, f.classId, f.students);
  await openAs(page, f.teacher, `/gv/classes/${f.classId}/matching`);
  const pending = page.waitForResponse(r => r.url().endsWith("/matching-rounds") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Chạy vòng ghép cặp" }).click();
  const round = await json<Schema<"RoundOut">>(await pending);
  expect(round.participantCount).toBe(2);
  expect(round.matches).toHaveLength(1);
  await expect(page.getByRole("status")).toContainText("Đã ghép 1 cặp từ 2 SV");
  for (const student of f.students) await expect(page.getByRole("region", { name: "Danh sách cặp" })).toContainText(student.fullName);
  return { ...f, matchId: round.matches[0].id };
}

test("MX4 (5:45–6:30) / FR-PM-01: SV bật và tắt tham gia trên UI", async ({ page, request }) => {
  const f = await prepare(request);
  await openAs(page, f.students[0], `/sv/classes/${f.classId}/peers`);
  const toggle = page.getByRole("switch", { name: "Tham gia ghép cặp" });
  await expect(toggle).toBeEnabled(); // Regression C2-14/GD-11; không skip để làm xanh.
  await expect(toggle).not.toBeChecked();
  for (const enabled of [true, false]) {
    const pending = page.waitForResponse(r => r.url().endsWith("/peer-opt-in") && r.request().method() === "PUT");
    await toggle.click();
    expect(await json(await pending)).toEqual({ peerOptIn: enabled });
    await page.reload();
    await expect(toggle).toBeChecked({ checked: enabled });
  }
});

for (const action of ["accept", "decline"] as const) {
  test(`MX4 (5:45–6:30) / FR-PM-05: SV thứ hai ${action} sau phản hồi đầu`, async ({ page, browser, request, baseURL }, info) => {
    // Lỗi đã biết, KHÔNG skip: tự đỏ khi được sửa ⇒ bỏ dòng test.fail.
    test.fail(true, "GD (Thắng) frontend/src/pages/student/SV07.tsx chỉ hiện Chấp nhận/Từ chối khi status PROPOSED; SV thứ hai thấy WAITING_OTHER + acceptedByMe=false nên không phản hồi được");
    const f = await preparePair(page, request);
    const contexts = await Promise.all(f.students.map(() => browser.newContext({ baseURL })));
    try {
      const pages = await Promise.all(contexts.map(context => context.newPage()));
      await openAs(pages[0], f.students[0], `/sv/classes/${f.classId}/peers`);
      const pending = pages[0].waitForResponse(r => r.url().endsWith(`/matches/${f.matchId}/accept`));
      await pages[0].getByRole("button", { name: "Chấp nhận", exact: true }).click();
      expect((await json<Schema<"MatchOut">>(await pending)).status).toBe("WAITING_OTHER");
      await openAs(pages[1], f.students[1], `/sv/classes/${f.classId}/peers`);
      const view = await json<Schema<"MatchOut">[]>(await request.get(`/api/v1/classes/${f.classId}/matches`, { headers: f.students[1].headers }));
      expect(view[0].acceptedByMe).toBe(false);
      await info.attach("second-student.json", { body: JSON.stringify({ classId: f.classId, matches: view }, null, 2), contentType: "application/json" });
      await expect(pages[1].getByRole("list", { name: "Cặp bạn cùng tiến" })).toBeVisible();
      await info.attach("waiting-other.png", { body: await pages[1].screenshot(), contentType: "image/png" });
      const button = pages[1].getByRole("button", { name: action === "accept" ? "Chấp nhận" : "Từ chối", exact: true });
      await expect(button).toBeVisible();
      const response = pages[1].waitForResponse(r => r.url().endsWith(`/matches/${f.matchId}/${action}`));
      await button.click();
      expect((await json<Schema<"MatchOut">>(await response)).status).toBe(action === "accept" ? "ACCEPTED" : "DECLINED");
    } finally { for (const context of contexts) await context.close(); }
  });
}

test("MX4 (5:45–6:30) / FR-PM-06/07: học cùng và hai phiên xác nhận lại trên UI", async ({ page, browser, request, baseURL }, info) => {
  test.setTimeout(120_000);
  const f = await preparePair(page, request);
  // API precondition tách FR-PM-05 đang lỗi; đây chưa phải demo UI xuyên suốt.
  for (const student of f.students) await json(await request.post(`/api/v1/matches/${f.matchId}/accept`, { headers: student.headers }));
  const contexts = await Promise.all(f.students.map(() => browser.newContext({ baseURL })));
  try {
    const pages = await Promise.all(contexts.map(context => context.newPage()));
    for (const [index, studentPage] of pages.entries()) {
      await openAs(studentPage, f.students[index], `/sv/classes/${f.classId}/peers`);
      const pending = studentPage.waitForResponse(r => r.url().endsWith(`/matches/${f.matchId}/studied`));
      await studentPage.getByRole("button", { name: "Đã học cùng", exact: true }).click();
      expect((await json<Schema<"MatchOut">>(await pending)).status).toBe(index === 0 ? "ACCEPTED" : "STUDIED");
    }
    for (const [index, studentPage] of pages.entries()) {
      await studentPage.reload(); // SV07 chưa đăng ký realtime cặp.
      const pending = studentPage.waitForResponse(r => r.url().endsWith("/sessions") && r.request().method() === "POST");
      await studentPage.getByRole("button", { name: /^Giảng lại .+ để xác nhận$/ }).click();
      const response = await pending;
      const created = await json<Schema<"SessionCreated">>(response);
      const peerItemId = response.request().postDataJSON().peerMatchItemId as string;
      expect(peerItemId).toBeTruthy();
      await studentPage.getByRole("tab", { name: "Văn bản", exact: true }).click();
      let reply: Schema<"TurnReply"> | undefined;
      for (let turn = 0; turn < 6 && reply?.status !== "COMPLETED"; turn++) {
        const first = turn === 0;
        await studentPage.getByRole("textbox", { name: first ? "Lời giảng của bạn" : "Câu trả lời của bạn" }).fill(first ? explanation : answer);
        const next = studentPage.waitForResponse(r => r.url().endsWith(`/sessions/${created.sessionId}/turns`) && r.request().method() === "POST");
        await studentPage.getByRole("button", { name: first ? "Gửi lời giảng" : "Gửi câu trả lời", exact: true }).click();
        reply = await json<Schema<"TurnReply">>(await next);
        if (reply.status === "CHALLENGING") await expect(studentPage.getByRole("textbox", { name: "Câu trả lời của bạn" })).toHaveValue("");
      }
      expect(reply?.status).toBe("COMPLETED");
      const result = await json<Schema<"SessionResult">>(await request.get(`/api/v1/sessions/${created.sessionId}/result`, { headers: f.students[index].headers }));
      expect(result.verdict).toBe("PASSED");
      expect(result.peerMatchItemId).toBe(peerItemId);
      expect(result.isPeerFollowup).toBe(true);
      await expect.poll(async () => {
        const matches = await json<Schema<"MatchOut">[]>(await request.get(`/api/v1/classes/${f.classId}/matches`, { headers: f.teacher.headers }));
        return matches[0].items.filter(item => item.verified).length;
      }, { timeout: 15_000 }).toBe(index + 1);
      await info.attach(`followup-${index + 1}.json`, { body: JSON.stringify({ classId: f.classId, matchId: f.matchId, sessionId: created.sessionId, peerItemId, verdict: result.verdict }), contentType: "application/json" });
    }
    await page.reload();
    await expect(page.getByRole("region", { name: "Danh sách cặp" })).toContainText("Đã xác nhận lại Đạt");
    await info.attach("verified.png", { body: await page.screenshot(), contentType: "image/png" });
  } finally { for (const context of contexts) await context.close(); }
});
