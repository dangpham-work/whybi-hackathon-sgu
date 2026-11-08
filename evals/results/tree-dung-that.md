# Đo dựng cây thật – đợt B (C1-20)

Công cụ: `evals/tree/dung_that.py` (LLM thật `gpt-4o-mini`, embedding `text-embedding-3-small`). Cùng đầu vào cho hai bản mã:
6 đoạn đầu kể từ chương 1, mức chi tiết STANDARD (trần 8 khái niệm mỗi đoạn). Đo ngày 2026-11-08.
"Trước" = commit `519f1f8` (chưa có đợt B); "Sau" = đợt B.

| Giáo trình | Bản | Nút | Cạnh thô (AI trả) | Cạnh sau rút gọn bắc cầu | Cạnh/nút | Cặp nút trùng tên | `call_json` | `embed` | Giây |
|---|---|---|---|---|---|---|---|---|---|
| Cần Thơ (109 trang) | Trước | 42 | 111 | 53 | 1,26 | 5 | 49 | 2 | 45 |
| Cần Thơ (109 trang) | Sau | 35 | 78 | 39 | 1,11 | 0 | 40 | 1 | 38 |
| Lê Minh Hoàng (316 trang) | Trước | 43 | 84 | 45 | 1,05 | 3 | 50 | 2 | 38 |
| Lê Minh Hoàng (316 trang) | Sau | 36 | 63 | 40 | 1,11 | 0 | 42 | 1 | 35 |

## Đọc kết quả

- **Hết nút trùng tên** (5 và 3 cặp → 0): gộp theo tên chuẩn hóa trước, rồi theo bản giống nhất.
- **Cạnh thô giảm 25–30 %** nhờ bỏ ứng viên không liên quan (cosine < 0,35) và so tên theo từ nguyên vẹn.
- **Chi phí giảm**: `call_json` −18 % (Cần Thơ), −16 % (Lê Minh Hoàng); `embed` từ 2 lượt còn 1.
- **Cạnh/nút sau rút gọn gần như không đổi (~1,1)**: đây là số GV nhìn thấy, vì `create_version(sanitize_graph=True)`
  đã rút gọn bắc cầu. Mục tiêu "cạnh/nút giảm ≥ 40 %" trong kế hoạch tính trên cạnh thô là chưa đạt (−10 % đến −16 % trên
  cạnh thô/nút); số lượng cạnh sau rút gọn đã sát mức tối thiểu của một DAG liên thông (~1 cạnh/nút).
- Chưa có cây chuẩn gắn giáo trình thật ⇒ **chưa đo được P/R/F1**; không chứng minh cạnh bị bỏ toàn là cạnh sai.
  Ngưỡng `MIN_CANDIDATE_COSINE = 0,35` là hằng số dễ chỉnh khi có `evaluate.py` trên cây chuẩn đã duyệt.

Mẫu nhỏ (2 giáo trình, 6 đoạn, 1 model); chạy lại khi đổi model hoặc ngưỡng.
