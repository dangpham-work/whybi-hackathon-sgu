import { expect, test } from "@playwright/test";

// KT-03 – smoke trên stack docker compose (nginx → SPA + api). Chạy trong CI job "e2e".

test("SMOKE-01 health qua nginx", async ({ request }) => {
  const res = await request.get("/health");
  expect(res.ok()).toBeTruthy();
  expect(await res.json()).toMatchObject({ status: "ok" });
});

test("SMOKE-02 API qua nginx trả lỗi đúng định dạng", async ({ request }) => {
  const res = await request.get("/api/v1/me");
  expect(res.status()).toBe(401);
  const body = await res.json();
  expect(body.error).toMatchObject({ code: "UNAUTHORIZED" });
});

test("SMOKE-03 mục lục màn hình hiển thị", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Whybi AI" })).toBeVisible();
  await expect(page.getByRole("link", { name: /GV-05 · Dashboard bản đồ nhiệt/ })).toBeVisible();
});

test("SMOKE-04 trang đăng nhập có ô email, mật khẩu và nút", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByLabel("Mật khẩu")).toBeVisible();
  await expect(page.getByRole("button", { name: "Đăng nhập" })).toBeVisible();
});
