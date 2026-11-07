---
description: Đẩy nhánh hiện tại và mở Pull Request theo mẫu của đội (cần gh auth login)
argument-hint: "[số issue]"
---

Issue liên quan: **$ARGUMENTS**

1. Kiểm tra: đang **không** ở `main`; tên nhánh dạng `feat/<mã>-…` hoặc `fix/<số>`; `git status` sạch.
2. `git fetch origin && git rebase origin/main` – xung đột thì dừng, báo file xung đột và chủ thư mục (bảng trong `AGENTS.md`).
3. Chạy `/kiemtra`. Đỏ thì dừng.
4. `git push -u origin HEAD` (không bao giờ `--force` lên nhánh của người khác; nhánh của mình sau rebase dùng `--force-with-lease`).
5. Tạo PR bằng `gh pr create --base main` với nội dung theo `.github/pull_request_template.md`:
   tiêu đề = commit chính (`<mã>: …`), mô tả gồm *Thẻ*, *Đã làm*, *Cách kiểm tra*, ảnh chụp nếu đổi giao diện, `Closes #$ARGUMENTS`.
6. Gắn reviewer là chủ thư mục bị chạm (theo `AGENTS.md` / `.github/CODEOWNERS`). Chỉ Long merge `main`.
7. In link PR.
