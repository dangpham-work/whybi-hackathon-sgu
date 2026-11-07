# Thẻ việc KT – Quyền (Kiểm tra bug & demo)

> Dán nguyên một thẻ làm prompt mở đầu phiên AI (hoặc dùng lệnh `/the <mã>` trong Claude Code).
> Trước khi code: đọc `AGENTS.md` và mọi file trong `docs/status/`.

## KT-01

- **Thẻ việc:** Mẫu issue bug (.github/ISSUE_TEMPLATE/bug.yml), nhãn P0/P1/P2 và nhãn module, bảng GitHub Projects
- **Yêu cầu / mục đề cương:** —
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-01
- **Giờ:** H0–H1
- **Xong khi:** Mở thử một issue có đủ trường
- **Người phụ trách:** Quyền
- **Nhánh:** `feat/kt-01-<mô-tả>` · commit bắt đầu bằng `KT-01:`

## KT-02

- **Thẻ việc:** Dữ liệu mẫu: lớp CTDL&GT, 1 GV, 1 QTV, 30 SV (tên giả), cây mẫu 8–10 nút theo schema của C2-02, 3–5 giáo trình mẫu (PDF, DOCX, 1 bản quét)
- **Yêu cầu / mục đề cương:** mục 7.5
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-02
- **Giờ:** H0–H2
- **Xong khi:** Thư mục seed/ nạp được bằng một lệnh
- **Người phụ trách:** Quyền
- **Nhánh:** `feat/kt-02-<mô-tả>` · commit bắt đầu bằng `KT-02:`

## KT-03

- **Thẻ việc:** Khung test tích hợp (pytest + httpx) và E2E (Playwright) chạy trong CI
- **Yêu cầu / mục đề cương:** mục 7.1, 7.3.1
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-01
- **Giờ:** H2–H3
- **Xong khi:** CI chạy cả test E2E
- **Người phụ trách:** Quyền
- **Nhánh:** `feat/kt-03-<mô-tả>` · commit bắt đầu bằng `KT-03:`

## KT-04

- **Thẻ việc:** Nạp các bộ đánh giá đã chuẩn bị vào evals/: 60–100 lời giảng có nhãn, ≥ 50 kịch bản tấn công, 30 đoạn ghi âm, 3–5 cây chuẩn
- **Yêu cầu / mục đề cương:** Bảng 7.3
- **Vòng:** 1 (M)
- **Phụ thuộc:** C1-01
- **Giờ:** H3–H4
- **Xong khi:** Script đọc được từng bộ theo schema
- **Người phụ trách:** Quyền
- **Nhánh:** `feat/kt-04-<mô-tả>` · commit bắt đầu bằng `KT-04:`

## KT-05

- **Thẻ việc:** Script giả lập 30 SV gửi kết quả qua API phiên thật, dồn lỗi vào nút N5 “Con trỏ” theo kịch bản demo
- **Yêu cầu / mục đề cương:** Bảng 7.4; Hình 7.2
- **Vòng:** 1 (M)
- **Phụ thuộc:** C1-01, C2-05
- **Giờ:** H4–H5
- **Xong khi:** Chạy script thì bảng thành thạo có dữ liệu của 30 SV
- **Người phụ trách:** Quyền
- **Nhánh:** `feat/kt-05-<mô-tả>` · commit bắt đầu bằng `KT-05:`

## KT-06

- **Thẻ việc:** Test chức năng MX2 theo Bảng 7.2 trên bản deploy: vào phiên, mở đầu, phản biện, chấm, kết quả; báo bug
- **Yêu cầu / mục đề cương:** FR-TB-01…04, 08, 12, 13; mục 7.3.2
- **Vòng:** 1 (M)
- **Phụ thuộc:** C1-07, GD-07
- **Giờ:** H7–H9
- **Xong khi:** Mọi lỗi tìm thấy đã thành issue có mức độ
- **Người phụ trách:** Quyền
- **Nhánh:** `feat/kt-06-<mô-tả>` · commit bắt đầu bằng `KT-06:`

## KT-07

- **Thẻ việc:** Chạy ≥ 50 kịch bản tấn công (Phụ lục B) vào Guard: tỉ lệ chặn, tỉ lệ Đạt sai; ghi vào evals/guard.md
- **Yêu cầu / mục đề cương:** FR-TB-09, 14; MT4
- **Vòng:** 1 (M)
- **Phụ thuộc:** C1-06
- **Giờ:** H9–H10
- **Xong khi:** Có số liệu (mục tiêu chặn ≥ 90%, Đạt sai 0%) và danh sách câu lọt qua
- **Người phụ trách:** Quyền
- **Nhánh:** `feat/kt-07-<mô-tả>` · commit bắt đầu bằng `KT-07:`

## KT-08

- **Thẻ việc:** Test bảo mật và phân quyền: JWT hết hạn, băm mật khẩu, SV không xem được kết quả của nhau, chỉ GV của lớp xem dữ liệu có tên, đồng ý ghi âm
- **Yêu cầu / mục đề cương:** FR-AD-01, 02; NFR-07, 08, 09
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-07
- **Giờ:** H10–H11
- **Xong khi:** Test phân quyền chạy xanh trong CI
- **Người phụ trách:** Quyền
- **Nhánh:** `feat/kt-08-<mô-tả>` · commit bắt đầu bằng `KT-08:`

## KT-09

- **Thẻ việc:** Test MX1: tải PDF, DOCX, bản quét; cây nháp; chặn chu trình; rubric; phát hành; đo P/R/F1 nút và cạnh so với cây chuẩn, thời gian sinh
- **Yêu cầu / mục đề cương:** FR-SK-01…09; MT1
- **Vòng:** 1 (M)
- **Phụ thuộc:** C1-11, GD-09
- **Giờ:** H11–H12
- **Xong khi:** Có F1 cạnh (mục tiêu ≥ 0,70) và thời gian sinh cây
- **Người phụ trách:** Quyền
- **Nhánh:** `feat/kt-09-<mô-tả>` · commit bắt đầu bằng `KT-09:`

## KT-10

- **Thẻ việc:** Test giọng nói: 30 đoạn ghi âm, WER, tỉ lệ thuật ngữ đúng, độ trễ STT; luồng ghi âm → xác nhận → gửi
- **Yêu cầu / mục đề cương:** FR-TB-05…07; NFR-02; Bảng 7.3
- **Vòng:** 1 (M)
- **Phụ thuộc:** C1-12, GD-08
- **Giờ:** H12–H13
- **Xong khi:** Có WER (mục tiêu ≤ 15%) và p95 độ trễ STT
- **Người phụ trách:** Quyền
- **Nhánh:** `feat/kt-10-<mô-tả>` · commit bắt đầu bằng `KT-10:`

## KT-11

- **Thẻ việc:** Test MX3, MX4 và chạy demo lần 1 (mốc M4): đổi màu ≤ 3 giây, truy vết gốc, ghép cặp theo ví dụ 6.6.4, xác nhận lại
- **Yêu cầu / mục đề cương:** FR-HM-01…06, FR-PM-01…07; NFR-03
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-13, C2-14, GD-10, GD-11
- **Giờ:** H13–H14
- **Xong khi:** Biên bản demo lần 1: đoạn nào quá giờ, lỗi nào
- **Người phụ trách:** Quyền
- **Nhánh:** `feat/kt-11-<mô-tả>` · commit bắt đầu bằng `KT-11:`

## KT-12

- **Thẻ việc:** Đánh giá Tutee trên 30 phiên mẫu: tỉ lệ câu hỏi lộ đáp án, tỉ lệ câu hỏi qua Guard ngay lần sinh đầu
- **Yêu cầu / mục đề cương:** NFR-06; Bảng 7.3
- **Vòng:** 2 (S)
- **Phụ thuộc:** C1-06
- **Giờ:** H14–H15
- **Xong khi:** Có số liệu (mục tiêu lộ đáp án ≤ 5%, qua Guard lần đầu ≥ 95%)
- **Người phụ trách:** Quyền
- **Nhánh:** `feat/kt-12-<mô-tả>` · commit bắt đầu bằng `KT-12:`

## KT-13

- **Thẻ việc:** Kiểm thử tải 20 / 50 / 100 phiên đồng thời bằng k6 hoặc Locust: p50/p95 độ trễ, tỉ lệ lỗi; đo hạ tầng với LLM_MODE=fake, đo độ trễ AI với 20 phiên dùng model thật; theo dõi chi phí token
- **Yêu cầu / mục đề cương:** NFR-01, 02, 04, 10, 13
- **Vòng:** 2 (S)
- **Phụ thuộc:** C2-04
- **Giờ:** H15–H17
- **Xong khi:** Có biểu đồ hộp độ trễ và tỉ lệ lỗi theo số phiên
- **Người phụ trách:** Quyền
- **Nhánh:** `feat/kt-13-<mô-tả>` · commit bắt đầu bằng `KT-13:`

## KT-14

- **Thẻ việc:** Test vòng 2: phiên bản cây, TTS, đếm giờ, hồ sơ SV, cấu hình, trình chiếu, ưu tiên nút nghẽn, điều chỉnh cặp, quản trị, thông báo; responsive và tiếp cận; chạy demo lần 2 ở H17
- **Yêu cầu / mục đề cương:** FR mức S; NFR-11, NFR-12
- **Vòng:** 2 (S)
- **Phụ thuộc:** Thẻ vòng 2
- **Giờ:** H17–H18
- **Xong khi:** Mọi lỗi đã thành issue; biên bản demo lần 2
- **Người phụ trách:** Quyền
- **Nhánh:** `feat/kt-14-<mô-tả>` · commit bắt đầu bằng `KT-14:`

## KT-15

- **Thẻ việc:** Test vòng 3: lịch sử phiên, nghe lại, xuất báo cáo
- **Yêu cầu / mục đề cương:** FR-TB-15, FR-HM-10
- **Vòng:** 3 (C)
- **Phụ thuộc:** C2-20, GD-16
- **Giờ:** H18–H19
- **Xong khi:** Báo cáo xuất ra đúng số liệu của lớp
- **Người phụ trách:** Quyền
- **Nhánh:** `feat/kt-15-<mô-tả>` · commit bắt đầu bằng `KT-15:`

## KT-16

- **Thẻ việc:** Kiểm tra phương án dự phòng (ngắt LLM, micro lỗi, hết hạn mức, sự cố máy chủ) và quay video dự phòng toàn kịch bản
- **Yêu cầu / mục đề cương:** Bảng 7.4
- **Vòng:** —
- **Phụ thuộc:** C1-13
- **Giờ:** H19–H21
- **Xong khi:** Video đủ 7 phút, lưu trên 2 máy
- **Người phụ trách:** Quyền
- **Nhánh:** `feat/kt-16-<mô-tả>` · commit bắt đầu bằng `KT-16:`

## KT-17

- **Thẻ việc:** Điền kết quả đánh giá thật vào Bảng 7.3 và mục 7.6 của đề cương; cập nhật Phụ lục D (khai báo công cụ AI)
- **Yêu cầu / mục đề cương:** mục 7.4, 7.6; Phụ lục D
- **Vòng:** —
- **Phụ thuộc:** KT-07…13, C1-16
- **Giờ:** H21–H22
- **Xong khi:** Bảng 7.3 không còn ô trống
- **Người phụ trách:** Quyền
- **Nhánh:** `feat/kt-17-<mô-tả>` · commit bắt đầu bằng `KT-17:`
