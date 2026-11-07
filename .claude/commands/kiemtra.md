---
description: Chạy toàn bộ lệnh kiểm tra (backend / frontend) cho phần vừa sửa và báo kết quả
argument-hint: "[backend|frontend|all]"
---

Phạm vi: **$ARGUMENTS** (để trống = tự chọn theo `git diff --name-only` so với `origin/main`).

1. Xác định file đã đổi: `git status --short` và `git diff --name-only origin/main...HEAD`.
2. Có file trong `backend/`:
   `cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest -q`
3. Có file trong `frontend/`:
   `cd frontend && npm run typecheck && npm test && npm run build`
4. Có file trong `backend/app/models/` hoặc `alembic/`: chạy thêm `uv run alembic check` (cần `docker compose up -d postgres`).
5. Báo kết quả dạng bảng (lệnh – xanh/đỏ). Lệnh đỏ: trích dòng lỗi chính, nêu nguyên nhân và đề xuất sửa –
   **không** tắt test, không thêm `# noqa` / `@ts-ignore` / `skip` để cho qua.
