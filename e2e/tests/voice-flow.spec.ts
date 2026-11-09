import { expect, test, type Page } from "@playwright/test";

// KT-10: UI thật + MediaRecorder thật, microphone Chromium giả và API có kịch bản.
// Kiểm API/Postgres riêng ở test_voice_flow.py; không dùng số đo này cho WER/NFR-02.
test.use({
  launchOptions: { args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"] },
  permissions: ["microphone"],
});

const sid = "10000000-0000-4000-8000-000000000010";
const transcript = "Biến là vùng nhớ có tên.";
declare global {
  interface Window { kt10MicRequests: number }
}
type MicWindow = Window;
type VoiceTurn = { inputMode: string; text: string; audioRef: string; transcriptEdited: boolean; sttConfidence: number };

async function prepare(page: Page, confidence = 0.95, unavailable = false) {
  const received = { uploads: [] as Buffer[], turns: [] as VoiceTurn[] };
  await page.addInitScript(() => {
    localStorage.setItem("whybi.token", "kt10-browser-fixture");
    const scope = window as MicWindow;
    scope.kt10MicRequests = 0;
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = (constraints) => {
      scope.kt10MicRequests += 1;
      return original(constraints);
    };
  });
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/me") {
      await route.fulfill({ json: { id: sid, fullName: "SV kiểm thử KT-10", email: "sv@whybi.test", role: "STUDENT" } });
    } else if (path === `/api/v1/sessions/${sid}/audio` && request.method() === "POST") {
      received.uploads.push(request.postDataBuffer()!);
      if (unavailable) {
        await route.fulfill({ status: 503, json: { error: { code: "STT_UNAVAILABLE", message: "STT test tạm lỗi", details: {} } } });
      } else {
        await route.fulfill({ json: {
          text: transcript, confidence, words: [{ word: "Biến", confidence }],
          lowConfidenceWords: confidence < 0.8 ? ["Biến"] : [],
          audioRef: `s3://audio/${sid}/fixture.webm`, needsConfirmation: confidence < 0.8,
        } });
      }
    } else if (path === `/api/v1/sessions/${sid}/turns` && request.method() === "POST") {
      received.turns.push(request.postDataJSON() as VoiceTurn);
      await route.fulfill({ json: { status: "CHALLENGING", questionsAsked: 1, questionsTotal: 3,
        question: { text: "Bạn giải thích thêm được không?" }, flags: [] } });
    } else {
      await route.fulfill({ status: 404, json: { error: { code: "FIXTURE_NOT_FOUND", message: "Ngoài fixture KT-10", details: {} } } });
    }
  });
  await page.goto(`/sv/sessions/${sid}`);
  // Main chưa khôi phục câu hỏi qua API: màn cho ghi tiếp sau khoảng chờ 6 giây (#120/GD-07).
  await expect(page.getByRole("button", { name: "Bắt đầu ghi âm", exact: true })).toBeEnabled({ timeout: 15_000 });
  return received;
}

async function record(page: Page, consent = true) {
  await page.getByRole("button", { name: "Bắt đầu ghi âm", exact: true }).click();
  if (consent) await page.getByRole("button", { name: "Đồng ý ghi âm", exact: true }).click();
  await expect(page.getByRole("button", { name: "Dừng ghi âm", exact: true })).toBeVisible();
  await expect(page.getByRole("img", { name: "Dạng sóng âm thanh" })).toBeVisible();
  await expect(page.getByText(/00:0[1-9] \/ 0[35]:00/)).toBeVisible();
  await page.getByRole("button", { name: "Dừng ghi âm", exact: true }).click();
  await expect(page.getByRole("button", { name: "Gửi bản ghi", exact: true })).toBeEnabled();
}

test("KT-10 / BR-13: từ chối ghi âm không xin micro và cho gõ chữ", async ({ page }) => {
  const received = await prepare(page);
  await page.getByRole("button", { name: "Bắt đầu ghi âm", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Cho phép ghi âm lời giảng?" })).toBeVisible();
  expect(await page.evaluate(() => (window as MicWindow).kt10MicRequests)).toBe(0);
  await page.getByRole("button", { name: "Không, tôi sẽ gõ chữ", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Lời giảng của bạn", exact: true })).toBeVisible();
  expect(await page.evaluate(() => (window as MicWindow).kt10MicRequests)).toBe(0);
  expect(received.uploads).toHaveLength(0);
  expect(received.turns).toHaveLength(0);
});

test("KT-10 / FR-TB-05: ghi, dừng, ghi lại rồi gửi bản ghi bằng VOICE", async ({ page }) => {
  const received = await prepare(page);
  await record(page);
  expect(received.uploads).toHaveLength(0);
  await page.getByRole("button", { name: "Ghi lại", exact: true }).click();
  await record(page, false);
  expect(await page.evaluate(() => (window as MicWindow).kt10MicRequests)).toBe(2);
  await page.getByRole("button", { name: "Gửi bản ghi", exact: true }).click();
  await expect.poll(() => received.turns.length).toBe(1);
  expect(received.uploads).toHaveLength(1);
  const multipart = received.uploads[0];
  expect(multipart.length).toBeGreaterThan(500);
  expect(multipart.includes(Buffer.from([0x1a, 0x45, 0xdf, 0xa3]))).toBeTruthy(); // WebM thật từ Chromium.
  expect(multipart.toString("latin1")).toMatch(/name="consent"\r\n\r\ntrue/);
  expect(received.turns[0]).toMatchObject({ inputMode: "VOICE", text: transcript,
    transcriptEdited: false, sttConfidence: 0.95, audioRef: `s3://audio/${sid}/fixture.webm` });
  await expect(page.getByRole("log", { name: "Hội thoại với Whybi" })).toContainText(transcript);
});

test("KT-10: STT lỗi không tự gửi lượt và giữ bản ghi để thử lại", async ({ page }) => {
  const received = await prepare(page, 0.95, true);
  await record(page);
  await page.getByRole("button", { name: "Gửi bản ghi", exact: true }).click();
  await expect(page.getByRole("alert").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Gửi bản ghi", exact: true })).toBeEnabled();
  expect(received.uploads).toHaveLength(1);
  expect(received.turns).toHaveLength(0);
});

test("KT-10 / TC07: confidence 0,65 phải xác nhận rồi mới gửi", async ({ page }) => {
  const received = await prepare(page, 0.65);
  await record(page);
  await page.getByRole("button", { name: "Gửi bản ghi", exact: true }).click();
  await expect.poll(() => received.uploads.length).toBe(1);
  // SV-05 (GD-08): confidence < 0,8 ⇒ hiện bảng kiểm tra bản chép lời, chưa gửi lượt nào.
  const dialog = page.getByRole("dialog", { name: "Kiểm tra bản chép lời" });
  await expect(dialog).toBeVisible();
  expect(received.turns).toHaveLength(0);
  await dialog.getByRole("button", { name: "Xác nhận và gửi" }).click();
  await expect.poll(() => received.turns.length).toBe(1);
  expect(received.turns[0]).toMatchObject({ inputMode: "VOICE", text: transcript, transcriptEdited: false, sttConfidence: 0.65 });
  await expect(dialog).toHaveCount(0);
});

test("KT-10 / FR-TB-05: đủ 3 phút thì tự dừng, không tự tải lên", async ({ page }) => {
  const received = await prepare(page);
  await page.clock.install();
  await page.getByRole("button", { name: "Bắt đầu ghi âm", exact: true }).click();
  await page.getByRole("button", { name: "Đồng ý ghi âm", exact: true }).click();
  await expect(page.getByRole("button", { name: "Dừng ghi âm", exact: true })).toBeVisible();
  await page.clock.fastForward(180_001);
  await expect(page.getByText("Đã đủ 3 phút – bản ghi tự dừng. Bấm Gửi hoặc Ghi lại.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Gửi bản ghi", exact: true })).toBeEnabled();
  expect(received.uploads).toHaveLength(0);
  expect(received.turns).toHaveLength(0);
});
