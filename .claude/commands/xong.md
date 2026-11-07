---
description: Kết thúc thẻ đang làm – kiểm tra, rà kiến trúc, cập nhật docs/status, commit đúng quy ước
argument-hint: <mã-thẻ>
---

Kết thúc thẻ **$ARGUMENTS**.

1. Mở lại thẻ `## $ARGUMENTS` trong `docs/cards/*.md`; đối chiếu từng ý của dòng **“Xong khi”** với code + test hiện có.
   Ý nào chưa đạt → liệt kê và dừng, không commit.
2. Chạy như lệnh `/kiemtra` – phải xanh hết.
3. Gọi subagent `kiem-kien-truc` rà `git diff` (luật trong `AGENTS.md`). Có vi phạm → sửa trước.
4. Kiểm tra không có bí mật: không có `.env`, khóa API, token trong diff.
5. Cập nhật `docs/status/<tên>.md` của người phụ trách thẻ (mẫu C.2): dòng *Xong*, *Phát sự kiện / hợp đồng đã chốt*, *Đang làm*, *Cần từ người khác*.
6. Đề xuất commit (chưa chạy nếu chưa được đồng ý):
   - nhánh `feat/<mã-thẻ viết thường>-<mô-tả-ngắn>` (đang ở `main` thì tạo nhánh trước);
   - message `$ARGUMENTS: <việc đã làm>` + dòng `Closes #<số issue>` nếu biết số issue.
7. Hỏi có tạo PR không (dùng `/pr`).
