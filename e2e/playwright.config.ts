import { defineConfig, devices } from "@playwright/test";

/**
 * E2E – Quyền (KT-03, KT-06, KT-09, KT-14). Chạy trên bản deploy chung (kế hoạch §1.2):
 *   E2E_BASE_URL=https://<tên-miền> npm test     (mặc định http://localhost – docker compose)
 */
export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "vi-VN",
  },
  projects: [
    { name: "gv-desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1024 } } },
    { name: "sv-mobile", use: { ...devices["Pixel 7"] }, testMatch: /sv-.*\.spec\.ts/ },
  ],
});
