---
description: Nạp một thẻ việc (vd. /the C1-05) cùng đặc tả và trạng thái đội, rồi lập kế hoạch
argument-hint: <mã-thẻ>
---

Thẻ cần làm: **$ARGUMENTS**

1. Đọc `AGENTS.md` và toàn bộ `docs/status/*.md`.
2. Tìm mục `## $ARGUMENTS` trong `docs/cards/*.md`; chép nguyên văn thẻ ra đây.
3. Từ dòng “Yêu cầu / mục đề cương”, mở **chỉ** file đặc tả liên quan trong `docs/spec/` (mx1…mx4, admin, api, data-model, ai-agents)
   và đúng các mục đề cương được nêu trong `docs/spec/outline/`.
4. Kiểm tra “Phụ thuộc”: thẻ phụ thuộc đã xong chưa (theo `docs/status/` và git log); chưa xong thì dùng dữ liệu mẫu / `LLM_MODE=fake`.
5. Đưa kế hoạch ngắn: file sẽ sửa (chỉ trong thư mục mình sở hữu), test sẽ viết theo “Xong khi”, điều nằm ngoài phạm vi.
   Nếu đụng > 3 file thì **dừng chờ duyệt**.
6. Sau khi làm xong: chạy lệnh kiểm tra trong `AGENTS.md`, cập nhật `docs/status/<tên>.md`, gợi ý nhánh `feat/<mã>-…` và commit `$ARGUMENTS: …`.
