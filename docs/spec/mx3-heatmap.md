# MX3 – Bản đồ nhiệt lớp học

> Bản tóm lược để làm việc. Nội dung gốc: [đề cương](README.md). Đổi hợp đồng ⇒ báo trong `docs/status/`.

## Yêu cầu chức năng

| Mã | Yêu cầu | Tác nhân | Ưu tiên |
|---|---|---|---|
| FR-HM-01 | Hiển thị bản đồ nhiệt dạng cây: màu mỗi nút theo tỉ lệ Đạt / đã thử | GV | M |
| FR-HM-02 | Hiển thị lưới SV × Nút có tên và MSSV, trạng thái từng ô, tiến độ mỗi SV | GV | M |
| FR-HM-03 | Cập nhật thời gian thực (≤ 3 giây) qua WebSocket | Hệ thống | M |
| FR-HM-04 | Phân biệt “chưa đủ mẫu / chưa thử” với “chưa đạt” | Hệ thống | M |
| FR-HM-05 | Truy vết và cảnh báo điểm nghẽn gốc (“Nên giảng lại X”) | Hệ thống | M |
| FR-HM-06 | Xem chi tiết nút: SV theo trạng thái (có tên), quan niệm sai phổ biến, nút gốc | GV | M |
| FR-HM-07 | Xem hồ sơ năng lực một SV và transcript / ghi âm các phiên | GV | S |
| FR-HM-08 | Cấu hình ngưỡng màu, cỡ mẫu tối thiểu, ngưỡng Đạt, số câu phản biện | GV | S |
| FR-HM-09 | Lọc, tìm theo tên; chế độ trình chiếu (có tùy chọn ẩn tên khi chiếu lên màn hình lớp) | GV | S |
| FR-HM-10 | Xuất báo cáo lớp CSV / PDF | GV | C |

## Đọc thêm trong đề cương

- 3.3.3 – [03-yeu-cau](outline/03-yeu-cau.md)
- 4.3.3, 4.4.4 – [04-phan-tich](outline/04-phan-tich.md)
- 5.2.6 Ma trận thành thạo, 5.4.3 Kênh realtime – [05-thiet-ke](outline/05-thiet-ke.md)
- 6.5 – [06-ai-thuat-toan](outline/06-ai-thuat-toan.md)

## Vị trí mã

- `backend/app/api/heatmap.py`
- `backend/app/algorithms/rootcause.py`
- `backend/app/workers/aggregation.py`
- `backend/app/realtime/`
- `backend/app/models/schemas/mastery.py`
- `frontend/src/components/HeatGrid.tsx`
- `frontend/src/pages/lecturer/ (GV-05a/b, GV-06)`

## Thẻ việc liên quan

| Thẻ | Người | Vòng | Nội dung |
|---|---|---|---|
| C1-15 | Đăng | 2 (S) | Đếm giờ trả lời mỗi câu và xử lý hết giờ; áp số câu phản biện và ngưỡng Đạt do GV cấu hình (đọc từ C2-17 khi xong) |
| C1-16 | Đăng | 2 (S) | Hiệu chỉnh Judge trên 60–100 lời giảng có nhãn: Cohen’s κ, ma trận nhầm lẫn; chỉnh rubric neo và số lần chấm |
| C2-06 | Long | 1 (M) | CSDL và migration Alembic theo danh sách bảng 5.2.3, từ điển dữ liệu 5.2.4, ràng buộc DAG 5.2.5, ma trận thành thạo 5.2.6 |
| C2-11 | Long | 1 (M) | Tổng hợp bản đồ nhiệt (hàng đợi aggregation): tỉ lệ Đạt trên số đã thử, cỡ mẫu tối thiểu, phân màu theo 6.5.2, tách “chưa đủ mẫu” với “chưa … |
| C2-12 | Long | 1 (M) | Truy vết điểm nghẽn gốc (6.5.3) và cảnh báo “Nên giảng lại X” |
| C2-13 | Long | 1 (M) | WebSocket class:{id}:heatmap (cell, node, alert); GET /classes/{id}/heatmap (cây và lưới có tên); GET /classes/{id}/nodes/{n}/detail |
| C2-17 | Long | 2 (S) | Hồ sơ năng lực SV kèm transcript và ghi âm (GET /classes/{id}/students/{s}/profile); cấu hình ngưỡng (PUT /classes/{id}/settings); lọc, tìm … |
| C2-20 | Long | 3 (C) | Lịch sử phiên của SV và nghe lại ghi âm; xuất báo cáo lớp CSV/PDF |
| KT-11 | Quyền | 1 (M) | Test MX3, MX4 và chạy demo lần 1 (mốc M4): đổi màu ≤ 3 giây, truy vết gốc, ghép cặp theo ví dụ 6.6.4, xác nhận lại |
| KT-15 | Quyền | 3 (C) | Test vòng 3: lịch sử phiên, nghe lại, xuất báo cáo |
| GD-10 | Thắng | 1 (M) | GV-05 Dashboard bản đồ nhiệt (chế độ cây, chế độ lưới SV × Nút có tên, cảnh báo điểm nghẽn) và GV-06 Chi tiết nút |
| GD-13 | Thắng | 2 (S) | GV-07 Hồ sơ năng lực SV; GV-08 Transcript, ghi âm, điểm từng tiêu chí, cờ vi phạm |
| GD-14 | Thắng | 2 (S) | GV-10 Cấu hình ngưỡng; lọc, tìm theo tên và chế độ trình chiếu ẩn tên ở GV-05; lịch sử, so sánh, khôi phục phiên bản ở GV-04 |
| GD-16 | Thắng | 3 (C) | SV-08 Lịch sử phiên và nghe lại; nút xuất báo cáo lớp CSV/PDF ở GV-05 |
