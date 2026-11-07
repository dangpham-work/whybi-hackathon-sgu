---
description: Tóm tắt tình hình cả đội – ai làm gì, hợp đồng nào đã chốt, ai đang chờ ai, thẻ nào làm tiếp
argument-hint: "[tên: dang|long|thang|quyen]"
---

Người hỏi: **$ARGUMENTS**

1. Đọc mọi file `docs/status/*.md`, `git log --oneline -20 origin/main` và (nếu có `gh`) `gh pr list --state open`.
2. Trình bày ngắn:
   - mỗi người: thẻ đang làm, thẻ vừa xong, đang cần gì;
   - hợp đồng / sự kiện đã chốt (schema, endpoint, kênh Pub/Sub) mà người khác có thể dùng ngay;
   - chỗ đang tắc (A chờ B) – đề xuất cách gỡ, ví dụ dùng `LLM_MODE=fake` hoặc dữ liệu mẫu.
3. Nếu có tên người hỏi: đề xuất **1 thẻ tiếp theo** trong `docs/cards/<tên>.md` có phụ thuộc đã xong, theo thứ tự vòng 1 → 2 → 3,
   và gợi ý chạy `/the <mã>`.
