# Thẻ việc GD – Thắng (Giao diện & slide)

> Dán nguyên một thẻ làm prompt mở đầu phiên AI (hoặc dùng lệnh `/the <mã>` trong Claude Code).
> Trước khi code: đọc `AGENTS.md` và mọi file trong `docs/status/`.

## GD-01

- **Thẻ việc:** Khung giao diện: layout GV, SV, QTV; điều hướng theo sơ đồ 5.5.1; route tự nạp; màu và font theo Figma; chú giải trạng thái bằng màu kèm biểu tượng; responsive từ 360 px
- **Yêu cầu / mục đề cương:** NFR-11, NFR-12; mục 5.5.1, 5.5.4
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-01
- **Giờ:** H0–H1
- **Xong khi:** Ba vai thấy đúng menu; mọi trạng thái có biểu tượng
- **Người phụ trách:** Thắng
- **Nhánh:** `feat/gd-01-<mô-tả>` · commit bắt đầu bằng `GD-01:`

## GD-02

- **Thẻ việc:** Kiểu dữ liệu sinh từ OpenAPI, lớp gọi API và WebSocket client dùng chung, xử lý trạng thái tải và lỗi
- **Yêu cầu / mục đề cương:** —
- **Vòng:** 1 (M)
- **Phụ thuộc:** C1-01, C2-02
- **Giờ:** H1–H2
- **Xong khi:** Build không lỗi kiểu; lỗi API hiện thông báo dễ hiểu
- **Người phụ trách:** Thắng
- **Nhánh:** `feat/gd-02-<mô-tả>` · commit bắt đầu bằng `GD-02:`

## GD-03

- **Thẻ việc:** Component SkillTree (React Flow): vẽ DAG, tự sắp xếp, tô màu theo trạng thái; dùng chung cho GV-04, GV-05, SV-02
- **Yêu cầu / mục đề cương:** —
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-02
- **Giờ:** H2–H3
- **Xong khi:** Cây mẫu hiển thị đúng thứ tự tiên quyết
- **Người phụ trách:** Thắng
- **Nhánh:** `feat/gd-03-<mô-tả>` · commit bắt đầu bằng `GD-03:`

## GD-04

- **Thẻ việc:** Đăng nhập, quên mật khẩu, hồ sơ; SV-01 Danh sách lớp và nhập mã tham gia
- **Yêu cầu / mục đề cương:** FR-AD-01, FR-TB-01
- **Vòng:** 1 (M)
- **Phụ thuộc:** GD-02, C2-07
- **Giờ:** H3–H4
- **Xong khi:** SV nhập mã 8 ký tự là vào được lớp
- **Người phụ trách:** Thắng
- **Nhánh:** `feat/gd-04-<mô-tả>` · commit bắt đầu bằng `GD-04:`

## GD-05

- **Thẻ việc:** GV-01 Danh sách lớp, GV-02 Tổng quan lớp, GV-03 Tải giáo trình và thanh tiến độ
- **Yêu cầu / mục đề cương:** FR-SK-01, 02, 03
- **Vòng:** 1 (M)
- **Phụ thuộc:** GD-02, C2-08
- **Giờ:** H4–H5
- **Xong khi:** Tải giáo trình thì thấy tiến độ cập nhật trực tiếp
- **Người phụ trách:** Thắng
- **Nhánh:** `feat/gd-05-<mô-tả>` · commit bắt đầu bằng `GD-05:`

## GD-06

- **Thẻ việc:** SV-02 Bản đồ học tập, SV-03 Chi tiết nút (trạng thái, điểm cao nhất, tiên quyết còn thiếu)
- **Yêu cầu / mục đề cương:** FR-TB-01, FR-TB-02
- **Vòng:** 1 (M)
- **Phụ thuộc:** GD-03, C2-10
- **Giờ:** H5–H6
- **Xong khi:** Từ đăng nhập đến bắt đầu phiên không quá 3 thao tác (NFR-11)
- **Người phụ trách:** Thắng
- **Nhánh:** `feat/gd-06-<mô-tả>` · commit bắt đầu bằng `GD-06:`

## GD-07

- **Thẻ việc:** SV-04 Phiên giảng lại: hội thoại, ô gõ (gửi sự kiện dán và tốc độ gõ), Recorder và Waveform ghi âm ≤ 3 phút, hỏi đồng ý trước khi ghi
- **Yêu cầu / mục đề cương:** FR-TB-03, 04, 05, 08; NFR-09
- **Vòng:** 1 (M)
- **Phụ thuộc:** GD-02, C1-07
- **Giờ:** H6–H8
- **Xong khi:** Một lượt giảng bằng giọng nói và một lượt bằng chữ đều gửi được
- **Người phụ trách:** Thắng
- **Nhánh:** `feat/gd-07-<mô-tả>` · commit bắt đầu bằng `GD-07:`

## GD-08

- **Thẻ việc:** SV-05 Xác nhận bản chép lời (gạch chân từ không chắc, cho sửa nhỏ); SV-06 Kết quả và phản hồi
- **Yêu cầu / mục đề cương:** FR-TB-06, 07, 13
- **Vòng:** 1 (M)
- **Phụ thuộc:** GD-07, C1-12
- **Giờ:** H8–H9
- **Xong khi:** Chỉnh sửa bản chép lời được ghi nhận; kết quả hiện đủ 5 tiêu chí
- **Người phụ trách:** Thắng
- **Nhánh:** `feat/gd-08-<mô-tả>` · commit bắt đầu bằng `GD-08:`

## GD-09

- **Thẻ việc:** GV-04 Trình sửa cây và rubric: kéo thả; thêm, sửa, xóa, gộp nút; thêm, xóa cạnh; báo chu trình theo đường đi; sửa, duyệt, sinh lại rubric; phát hành
- **Yêu cầu / mục đề cương:** FR-SK-04…09
- **Vòng:** 1 (M)
- **Phụ thuộc:** GD-03, C2-09, C1-11
- **Giờ:** H9–H10
- **Xong khi:** Tạo chu trình thì thông báo chỉ rõ đường đi
- **Người phụ trách:** Thắng
- **Nhánh:** `feat/gd-09-<mô-tả>` · commit bắt đầu bằng `GD-09:`

## GD-10

- **Thẻ việc:** GV-05 Dashboard bản đồ nhiệt (chế độ cây, chế độ lưới SV × Nút có tên, cảnh báo điểm nghẽn) và GV-06 Chi tiết nút
- **Yêu cầu / mục đề cương:** FR-HM-01…06
- **Vòng:** 1 (M)
- **Phụ thuộc:** GD-03, C2-13
- **Giờ:** H10–H12
- **Xong khi:** Chạy script giả lập thì màn đổi màu mà không cần tải lại
- **Người phụ trách:** Thắng
- **Nhánh:** `feat/gd-10-<mô-tả>` · commit bắt đầu bằng `GD-10:`

## GD-11

- **Thẻ việc:** GV-09 Quản lý ghép cặp (chạy vòng, danh sách cặp); SV-07 Bạn cùng tiến (bật/tắt tham gia, gợi ý, chấp nhận, từ chối, “Đã học cùng”)
- **Yêu cầu / mục đề cương:** FR-PM-01, 02, 05, 06, 07
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-14
- **Giờ:** H12–H13
- **Xong khi:** Hiện đúng cặp An ↔ Châu theo dữ liệu mẫu
- **Người phụ trách:** Thắng
- **Nhánh:** `feat/gd-11-<mô-tả>` · commit bắt đầu bằng `GD-11:`

## GD-12

- **Thẻ việc:** SV-04: nút bật TTS và đồng hồ đếm giờ; GV-09: điều chỉnh cặp thủ công và thống kê
- **Yêu cầu / mục đề cương:** FR-TB-10, 11; FR-PM-08
- **Vòng:** 2 (S)
- **Phụ thuộc:** C1-14, C1-15, C2-15
- **Giờ:** H13–H14
- **Xong khi:** Đồng hồ về 0 thì câu được ghi nhận hết giờ
- **Người phụ trách:** Thắng
- **Nhánh:** `feat/gd-12-<mô-tả>` · commit bắt đầu bằng `GD-12:`

## GD-13

- **Thẻ việc:** GV-07 Hồ sơ năng lực SV; GV-08 Transcript, ghi âm, điểm từng tiêu chí, cờ vi phạm
- **Yêu cầu / mục đề cương:** FR-HM-07, FR-TB-14
- **Vòng:** 2 (S)
- **Phụ thuộc:** C2-17
- **Giờ:** H14–H15
- **Xong khi:** GV mở được transcript và nghe ghi âm của một phiên
- **Người phụ trách:** Thắng
- **Nhánh:** `feat/gd-13-<mô-tả>` · commit bắt đầu bằng `GD-13:`

## GD-14

- **Thẻ việc:** GV-10 Cấu hình ngưỡng; lọc, tìm theo tên và chế độ trình chiếu ẩn tên ở GV-05; lịch sử, so sánh, khôi phục phiên bản ở GV-04
- **Yêu cầu / mục đề cương:** FR-HM-08, 09; FR-SK-10
- **Vòng:** 2 (S)
- **Phụ thuộc:** C2-16, C2-17
- **Giờ:** H15–H16
- **Xong khi:** Bật chế độ trình chiếu thì lưới ẩn tên SV
- **Người phụ trách:** Thắng
- **Nhánh:** `feat/gd-14-<mô-tả>` · commit bắt đầu bằng `GD-14:`

## GD-15

- **Thẻ việc:** Màn quản trị (bổ sung, chưa có trong Bảng 5.12): tài khoản và nhập CSV, danh mục môn, cấu hình nhà cung cấp AI, hạn mức, nhật ký và cờ vi phạm; thông báo trong ứng dụng
- **Yêu cầu / mục đề cương:** FR-AD-03…08
- **Vòng:** 2 (S)
- **Phụ thuộc:** C2-18, C2-19, C1-02
- **Giờ:** H16–H17
- **Xong khi:** QTV đổi được model dự phòng từ giao diện
- **Người phụ trách:** Thắng
- **Nhánh:** `feat/gd-15-<mô-tả>` · commit bắt đầu bằng `GD-15:`

## GD-16

- **Thẻ việc:** SV-08 Lịch sử phiên và nghe lại; nút xuất báo cáo lớp CSV/PDF ở GV-05
- **Yêu cầu / mục đề cương:** FR-TB-15, FR-HM-10
- **Vòng:** 3 (C)
- **Phụ thuộc:** C2-20
- **Giờ:** H17–H18
- **Xong khi:** Tải được báo cáo; nghe lại được ghi âm
- **Người phụ trách:** Thắng
- **Nhánh:** `feat/gd-16-<mô-tả>` · commit bắt đầu bằng `GD-16:`

## GD-17

- **Thẻ việc:** Chốt slide: ảnh chụp thật, số liệu đo trong evals/, xuất PDF để nộp
- **Yêu cầu / mục đề cương:** —
- **Vòng:** —
- **Phụ thuộc:** KT-12, KT-13
- **Giờ:** H18–H20
- **Xong khi:** Slide nộp trước hạn của quy chế
- **Người phụ trách:** Thắng
- **Nhánh:** `feat/gd-17-<mô-tả>` · commit bắt đầu bằng `GD-17:`
