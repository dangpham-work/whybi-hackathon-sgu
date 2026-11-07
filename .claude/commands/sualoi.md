---
description: Sửa một bug theo quy trình – viết test tái hiện trước, sửa tối thiểu, nhánh fix/<số>
argument-hint: <số-issue hoặc mô tả lỗi>
---

Lỗi: **$ARGUMENTS**

1. Nếu là số issue: `gh issue view $ARGUMENTS` để lấy mô tả, bước tái hiện, mức P0/P1/P2.
2. Xác định thư mục chứa lỗi và chủ của nó (bảng trong `AGENTS.md`). Không phải thư mục của mình → soạn tin nhắn cho chủ thư mục thay vì sửa.
3. Tạo nhánh `fix/<số-issue>` từ `origin/main` mới nhất.
4. **Viết test tái hiện trước** (backend: `backend/tests/…`, frontend: `frontend/src/**/*.test.ts(x)`, luồng: `e2e/tests/`) – chạy để thấy nó ĐỎ.
5. Tìm nguyên nhân gốc (đọc log `docker compose logs <dịch vụ>` nếu cần) – giải thích ngắn trước khi sửa.
6. Sửa tối thiểu cho test XANH; không refactor lan rộng.
7. Chạy `/kiemtra`; commit `fix #<số>: <mô tả>`; gợi ý `/pr <số>`.
