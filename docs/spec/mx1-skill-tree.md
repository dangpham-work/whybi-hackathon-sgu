# MX1 – Cây kỹ năng

> Bản tóm lược để làm việc. Nội dung gốc: [đề cương](README.md). Đổi hợp đồng ⇒ báo trong `docs/status/`.

## Yêu cầu chức năng

| Mã | Yêu cầu | Tác nhân | Ưu tiên |
|---|---|---|---|
| FR-SK-01 | Tạo lớp học phần (môn, học kỳ, tên lớp), sinh mã tham gia 8 ký tự | GV | M |
| FR-SK-02 | Tải giáo trình PDF/DOCX ≤ 20 MB; kiểm tra định dạng, dung lượng | GV | M |
| FR-SK-03 | Phân tích tài liệu nền, hiển thị tiến độ theo thời gian thực; OCR khi là bản quét | Hệ thống | M |
| FR-SK-04 | Trích xuất khái niệm, suy luận quan hệ tiên quyết, đảm bảo kết quả là DAG | Hệ thống | M |
| FR-SK-05 | Sinh rubric cho từng nút: ý chính bắt buộc, quan niệm sai, tình huống phản biện, mức Bloom, có trích dẫn trang | Hệ thống | M |
| FR-SK-06 | Trình sửa cây kéo thả: thêm / sửa / xóa / gộp nút, thêm / xóa cạnh, tự sắp xếp | GV | M |
| FR-SK-07 | Chặn thao tác tạo chu trình và chỉ rõ đường đi của chu trình | Hệ thống | M |
| FR-SK-08 | Duyệt / sửa rubric; sinh lại rubric bằng AI cho một nút | GV | M |
| FR-SK-09 | Phát hành cây; khởi tạo hoặc di chuyển trạng thái thành thạo của SV | GV, Hệ thống | M |
| FR-SK-10 | Quản lý phiên bản: xem lịch sử, so sánh, khôi phục | GV | S |

## Đọc thêm trong đề cương

- 3.3.1 Yêu cầu chức năng – [03-yeu-cau](outline/03-yeu-cau.md)
- UC liên quan, 4.3.1, 4.4.1–4.4.2, 4.5.3 – [04-phan-tich](outline/04-phan-tich.md)
- 6.1 Trích xuất cây kỹ năng – [06-ai-thuat-toan](outline/06-ai-thuat-toan.md)
- 5.2.5 Lưu trữ DAG – [05-thiet-ke](outline/05-thiet-ke.md)

## Vị trí mã

- `backend/app/api/trees.py`
- `backend/app/api/classes.py`
- `backend/app/services/`
- `backend/app/algorithms/dag.py`
- `backend/app/workers/documents.py`
- `backend/app/models/tree.py`
- `backend/app/models/schemas/tree.py`
- `frontend/src/components/SkillTree.tsx`
- `frontend/src/pages/lecturer/ (GV-02…GV-04)`

## Thẻ việc liên quan

| Thẻ | Người | Vòng | Nội dung |
|---|---|---|---|
| C1-04 | Đăng | 1 (M) | Sinh 3–5 câu hỏi phản biện theo 4 chiến lược (ý thiếu, quan niệm sai, tình huống biên, chuyển giao) từ rubric và lời giảng |
| C1-05 | Đăng | 1 (M) | Judge: chấm 5 tiêu chí (6.3.1), công thức điểm và quy tắc Đạt BR-03 (6.3.2), giảm thiên lệch bằng rubric neo và chấm nhiều lần (6.3.3), phản… |
| C1-09 | Đăng | 1 (M) | Tiền xử lý giáo trình (tác vụ Celery, hàng đợi documents): PyMuPDF, python-docx, OCR Tesseract tiếng Việt cho bản quét; báo tiến độ qua kênh… |
| C1-10 | Đăng | 1 (M) | Trích khái niệm và suy luận quan hệ tiên quyết; giao đồ thị cho bước hậu xử lý DAG (C2-09) |
| C1-11 | Đăng | 1 (M) | Sinh rubric từng nút (ý chính bắt buộc, quan niệm sai, tình huống phản biện, mức Bloom, trích dẫn trang); sinh lại rubric 1 nút (POST /nodes… |
| C1-13 | Đăng | 1 (M) | Chế độ demo: cây và câu hỏi lưu sẵn (DEMO_MODE=1), khóa API và model dự phòng cấu hình sẵn |
| C1-16 | Đăng | 2 (S) | Hiệu chỉnh Judge trên 60–100 lời giảng có nhãn: Cohen’s κ, ma trận nhầm lẫn; chỉnh rubric neo và số lần chấm |
| C2-02 | Long | 1 (M) | Schema cây app/models/schemas/tree.py (Node, Edge, Rubric, TreeVersion); nạp cây mẫu CTDL&GT do Quyền soạn; GET /classes/{id}/tree |
| C2-06 | Long | 1 (M) | CSDL và migration Alembic theo danh sách bảng 5.2.3, từ điển dữ liệu 5.2.4, ràng buộc DAG 5.2.5, ma trận thành thạo 5.2.6 |
| C2-08 | Long | 1 (M) | Lớp học phần, mã tham gia 8 ký tự, SV tham gia lớp; tải giáo trình PDF/DOCX ≤ 20 MB lên MinIO (kiểm tra định dạng, dung lượng); tạo job và k… |
| C2-09 | Long | 1 (M) | API cây theo Bảng 5.10: thêm, sửa nút; thêm cạnh có kiểm tra chu trình và trả đường đi; xóa cạnh; sửa và duyệt rubric; hậu xử lý DAG bằng Ne… |
| C2-10 | Long | 1 (M) | MasteryService: phát hành thì khởi tạo hoặc di chuyển trạng thái SV sang phiên bản mới; nhận session.completed thì cập nhật theo 4.5.1 và ph… |
| C2-13 | Long | 1 (M) | WebSocket class:{id}:heatmap (cell, node, alert); GET /classes/{id}/heatmap (cây và lưới có tên); GET /classes/{id}/nodes/{n}/detail |
| C2-16 | Long | 2 (S) | Quản lý phiên bản cây: lịch sử, so sánh, khôi phục |
| KT-02 | Quyền | 1 (M) | Dữ liệu mẫu: lớp CTDL&GT, 1 GV, 1 QTV, 30 SV (tên giả), cây mẫu 8–10 nút theo schema của C2-02, 3–5 giáo trình mẫu (PDF, DOCX, 1 bản quét) |
| KT-04 | Quyền | 1 (M) | Nạp các bộ đánh giá đã chuẩn bị vào evals/: 60–100 lời giảng có nhãn, ≥ 50 kịch bản tấn công, 30 đoạn ghi âm, 3–5 cây chuẩn |
| KT-09 | Quyền | 1 (M) | Test MX1: tải PDF, DOCX, bản quét; cây nháp; chặn chu trình; rubric; phát hành; đo P/R/F1 nút và cạnh so với cây chuẩn, thời gian sinh |
| KT-14 | Quyền | 2 (S) | Test vòng 2: phiên bản cây, TTS, đếm giờ, hồ sơ SV, cấu hình, trình chiếu, ưu tiên nút nghẽn, điều chỉnh cặp, quản trị, thông báo; responsiv… |
| GD-03 | Thắng | 1 (M) | Component SkillTree (React Flow): vẽ DAG, tự sắp xếp, tô màu theo trạng thái; dùng chung cho GV-04, GV-05, SV-02 |
| GD-05 | Thắng | 1 (M) | GV-01 Danh sách lớp, GV-02 Tổng quan lớp, GV-03 Tải giáo trình và thanh tiến độ |
| GD-09 | Thắng | 1 (M) | GV-04 Trình sửa cây và rubric: kéo thả; thêm, sửa, xóa, gộp nút; thêm, xóa cạnh; báo chu trình theo đường đi; sửa, duyệt, sinh lại rubric; p… |
| GD-10 | Thắng | 1 (M) | GV-05 Dashboard bản đồ nhiệt (chế độ cây, chế độ lưới SV × Nút có tên, cảnh báo điểm nghẽn) và GV-06 Chi tiết nút |
| GD-14 | Thắng | 2 (S) | GV-10 Cấu hình ngưỡng; lọc, tìm theo tên và chế độ trình chiếu ẩn tên ở GV-05; lịch sử, so sánh, khôi phục phiên bản ở GV-04 |
