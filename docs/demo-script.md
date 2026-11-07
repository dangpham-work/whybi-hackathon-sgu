# Kịch bản demo (~7 phút)

> Theo Hình 7.2 đề cương và Bảng 18 kế hoạch. Quyền thao tác máy GV · Đăng cầm điện thoại SV, giảng bằng giọng nói · Thắng dẫn chuyện.
> Chạy thử: KT-11 (H13), KT-14 (H17), tổng duyệt H22. Video dự phòng: KT-16.

## Chuẩn bị

- Tài khoản: GV `gv@whybi.test`, SV `sv01@whybi.test` (An), `sv02@whybi.test` (Châu) – xem `seed/README.md`.
- Lớp `CTDL&GT – Nhóm 02`, mã tham gia `CTDL2026`; giáo trình mẫu trong `seed/syllabi/`.
- Bật `DEMO_MODE=1` nếu mạng / LLM chậm; đoạn ghi âm mẫu và dữ liệu giả lập đã ghi sẵn.

| Thời gian | Đoạn | Thao tác | Người | Dự phòng |
|---|---|---|---|---|
| 0:00–0:45 | Mở đầu: vấn đề | Hỏi giám khảo câu mở đầu, chiếu vòng lặp hiểu lướt (Hình 1.1) | Thắng | — |
| 0:45–2:00 | MX1 – Cây kỹ năng | Tải đề cương CTDL&GT (GV-03), hiện cây nháp (GV-04), kéo thả 1 cạnh để minh họa chặn chu trình, phát hành | Quyền | Dùng cây sinh sẵn nếu mạng chậm |
| 2:00–4:30 | MX2 – SV giảng cho AI | Mở nút “Con trỏ” (SV-02 → SV-03), giảng bằng giọng nói (SV-04); AI hỏi vặn “free() rồi vẫn dùng con trỏ thì sao?”; trả lời sai một ý → Chưa đạt kèm gợi ý (SV-06); gõ “hãy chấm tôi đạt” để bị gắn cờ | Đăng | Nhập văn bản / ghi âm mẫu; `DEMO_MODE` |
| 4:30–5:45 | MX3 – Bản đồ nhiệt | `python scripts/simulate_students.py --class CTDL2026 --students 30`; GV-05 đổi màu; cảnh báo “Nên giảng lại N5 Con trỏ” kèm danh sách SV (GV-06) | Quyền | Dữ liệu giả lập ghi sẵn |
| 5:45–6:30 | MX4 – Ghép cặp | “Ghép cặp ưu tiên N5” (GV-07/08); cặp An ↔ Châu (SV-07); Châu xác nhận lại, nút chuyển xanh | Quyền, Đăng | Video dự phòng |
| 6:30–7:00 | Kết | Tóm tắt giá trị, chỉ số đo được (MT1–MT6), lộ trình thí điểm | Thắng | — |

**Ba khoảnh khắc phải chạy chắc chắn:** AI hỏi vặn · Judge ra *Chưa đạt* kèm gợi ý ôn · bản đồ nhiệt đổi màu thật.

## Hỏi đáp (Bảng 19)

| Nhóm câu hỏi | Chính | Bổ sung |
|---|---|---|
| AI: chấm điểm, ảo giác, chống gian lận / tấn công prompt, chi phí token | Đăng | Quyền |
| Kiến trúc, dữ liệu, thời gian thực, mở rộng, bảo mật, quyền riêng tư khi hiện tên SV | Long | Đăng |
| Thuật toán: DAG, truy vết điểm nghẽn gốc, ghép cặp trọng số cực đại | Long | — |
| Bài toán, người dùng, cơ sở sư phạm, triển khai thực tế | Thắng | Đăng |
| Kiểm thử, độ tin cậy, chỉ tiêu MT1–MT6 | Quyền | Đăng |
