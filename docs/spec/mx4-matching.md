# MX4 – Ghép cặp bạn cùng tiến

> Bản tóm lược để làm việc. Nội dung gốc: [đề cương](README.md). Đổi hợp đồng ⇒ báo trong `docs/status/`.

## Yêu cầu chức năng

| Mã | Yêu cầu | Tác nhân | Ưu tiên |
|---|---|---|---|
| FR-PM-01 | SV bật / tắt tham gia ghép cặp | SV | M |
| FR-PM-02 | Chạy vòng ghép cặp theo lệnh GV hoặc định kỳ | GV, Bộ hẹn giờ | M |
| FR-PM-03 | Tính trọng số bù trừ hai chiều, giải ghép cặp trọng số cực đại | Hệ thống | M |
| FR-PM-04 | Ưu tiên nút đang là điểm nghẽn của lớp | Hệ thống | S |
| FR-PM-05 | Gửi gợi ý (hạn 48 giờ): bạn ghép, nút mình dạy, nút mình học; chấp nhận / từ chối | SV | M |
| FR-PM-06 | Đánh dấu “Đã học cùng”; mở yêu cầu xác nhận lại | SV, Hệ thống | M |
| FR-PM-07 | Xác nhận lại bằng phiên giảng lại; cập nhật trạng thái cặp | SV, Hệ thống | M |
| FR-PM-08 | GV xem danh sách cặp, điều chỉnh thủ công, thống kê hiệu quả | GV | S |

## Đọc thêm trong đề cương

- 3.3.4 – [03-yeu-cau](outline/03-yeu-cau.md)
- 4.3.4, 4.4.5, 4.5.4 – [04-phan-tich](outline/04-phan-tich.md)
- 6.6 – [06-ai-thuat-toan](outline/06-ai-thuat-toan.md)

## Vị trí mã

- `backend/app/api/matching.py`
- `backend/app/algorithms/matching.py`
- `backend/app/workers/matching.py`
- `backend/app/models/peer.py`
- `frontend/src/pages/lecturer/ (GV-07, GV-08)`
- `frontend/src/pages/student/ (SV-07, SV-08)`

## Thẻ việc liên quan

| Thẻ | Người | Vòng | Nội dung |
|---|---|---|---|
| C1-07 | Đăng | 1 (M) | SessionOrchestrator theo 4.5.2: POST /sessions, /sessions/{id}/turns, /sessions/{id}/timeout, GET /sessions/{id}/result; kênh session:{id}; … |
| C2-03 | Long | 1 (M) | Docker Compose đủ dịch vụ theo Bảng 5.15: nginx, api (uvicorn × 4), worker (hàng đợi documents, aggregation, matching, ai), beat, postgres 1… |
| C2-14 | Long | 1 (M) | Ghép cặp: bật/tắt tham gia; trọng số bù trừ hai chiều (6.6.2); max_weight_matching; chạy theo lệnh GV và định kỳ bằng Celery beat; gợi ý hạn… |
| C2-15 | Long | 2 (S) | Ưu tiên nút đang nghẽn khi ghép; GV điều chỉnh cặp thủ công và xem thống kê hiệu quả (6.6.6) |
| KT-11 | Quyền | 1 (M) | Test MX3, MX4 và chạy demo lần 1 (mốc M4): đổi màu ≤ 3 giây, truy vết gốc, ghép cặp theo ví dụ 6.6.4, xác nhận lại |
| KT-14 | Quyền | 2 (S) | Test vòng 2: phiên bản cây, TTS, đếm giờ, hồ sơ SV, cấu hình, trình chiếu, ưu tiên nút nghẽn, điều chỉnh cặp, quản trị, thông báo; responsiv… |
| GD-11 | Thắng | 1 (M) | GV-09 Quản lý ghép cặp (chạy vòng, danh sách cặp); SV-07 Bạn cùng tiến (bật/tắt tham gia, gợi ý, chấp nhận, từ chối, “Đã học cùng”) |
| GD-12 | Thắng | 2 (S) | SV-04: nút bật TTS và đồng hồ đếm giờ; GV-09: điều chỉnh cặp thủ công và thống kê |
