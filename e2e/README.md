# E2E (Playwright) – Quyền

```bash
cd e2e
npm ci && npx playwright install chromium   # Linux/CI: npm run install:browsers (kèm --with-deps)
npm test                                    # http://localhost (docker compose)
E2E_BASE_URL=https://<tên-miền> npm test    # bản deploy chung
npm run typecheck                           # tsc --noEmit, không cần stack
npx playwright test --list                  # liệt kê test, không cần stack
```

Dự án `gv-desktop` (1440×1024) chạy mọi test; `sv-mobile` (Pixel 7) chạy `sv-*.spec.ts`.

CI: job `e2e` trong `.github/workflows/ci.yml` dựng `docker compose` (LLM_MODE=fake), chạy test tích hợp
(`backend/tests/integration`, `-m integration`) rồi `npx playwright test`; báo cáo HTML tải ở artifact `playwright-report`.
Job chạy song song, tạm không chặn PR (`continue-on-error`).
