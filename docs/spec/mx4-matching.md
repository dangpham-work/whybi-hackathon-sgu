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

## Ghép theo sự kiện trong hạn kiểm tra bài cũ (C2-15)

Bổ sung cho vòng ghép lô (Blossom, 6.6). GV đặt **hạn kiểm tra bài cũ** cho từng nút của lớp
(`PUT /classes/{id}/nodes/{nodeId}/review-window`, xem lại bằng `GET /classes/{id}/review-windows`). Trong hạn, ghép cặp chạy
**ngay khi có kết quả**, không đợi cả lớp làm xong:

- SV **Đạt** nút ⇒ thành người dạy; SV **không đạt** ⇒ ghép ngay với người dạy còn chỗ, chưa có ⇒ vào hàng chờ,
  có người Đạt mới thì bạn chờ được ghép theo thứ tự đến trước.
- **Một người Đạt dạy tối đa 3 người chưa Đạt** (`TEACH_LIMIT`). Người học vào người dạy đang kèm ít nhất, hòa thì người Đạt sớm hơn.
- Không còn cổng tỉ lệ Đạt. Không ghép lại cặp vừa từ chối trong 14 ngày. Chỉ SV đã bật ghép cặp (BR-10) tham gia.
- Bạn đang chờ mà **tự Đạt** thì cặp chờ của họ bị hủy (họ thành người dạy). Hết hạn thì dừng ghép tự động;
  `GET review-windows` cho GV thấy bạn còn chờ để giảng trực tiếp.
- Mỗi cặp là một `peer_matches` (người dạy = A, người học = B, một mục dạy A → B) nên chấp nhận / học cùng / xác nhận lại như cũ.
  Vòng ghép của các cặp này có `trigger_type = LIVE`.
- Kích hoạt: sự kiện `mastery.changed` (xử lý ở tiến trình `mastery_listener`) và beat `live_rebalance` mỗi 60 giây (bù tin mất,
  bù người dạy mới). Lớp đang có hạn mở **không** chạy ghép lô hằng ngày 06:00.
- Code: `algorithms/live_matching.py` (hàm thuần `assign`), `services/live_matching.py`, bảng `node_review_windows`.

## Ưu tiên nút nghẽn, điều chỉnh cặp, thống kê (C2-15 phần 2)

- **Ưu tiên nút**: `POST /classes/{id}/matching-rounds {priorityNodeId}` cộng thêm 10 vào độ ưu tiên p(n) của nút đó (cả ghép hai chiều lẫn
  một chiều), nên cặp có người dạy nút đó thắng khi tranh người. Nút không thuộc cây đang phát hành ⇒ 404 `NODE_NOT_IN_TREE`.
- **GV điều chỉnh cặp** `PATCH /matches/{id}`: `{cancel: true}` hủy cặp (⇒ `DECLINED`) hoặc `{replaceStudentId, withStudentId}` thay một SV
  bằng SV khác đã bật ghép cặp và chưa ở cặp hoạt động nào. Nút dạy / học tính lại từ ma trận hiện tại (tối đa 2 nút mỗi chiều), hai SV không
  có gì để dạy nhau ⇒ 422 `NO_COMPLEMENTARY_NODES`; cặp quay về `PROPOSED`, hạn 48 giờ, hai bên chấp nhận lại. Chỉ cặp đang hoạt động.
- **Thống kê** `GET /classes/{id}/matching-stats` (6.6.6): tỉ lệ chấp nhận (cả hai chấp nhận / tổng cặp), tỉ lệ học cùng (cả hai bấm / đã chấp nhận),
  tỉ lệ mục dạy–học được xác nhận Đạt (trong các cặp đã học cùng). So sánh với SV tự ôn (thí điểm) chưa làm.

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
