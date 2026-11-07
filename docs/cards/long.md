# Thẻ việc C2 – Long (Code chính 2: Nền tảng)

> Dán nguyên một thẻ làm prompt mở đầu phiên AI (hoặc dùng lệnh `/the <mã>` trong Claude Code).
> Trước khi code: đọc `AGENTS.md` và mọi file trong `docs/status/`.

## C2-01

- **Thẻ việc:** Khởi tạo repo theo cấu trúc mục 7.2: FastAPI tự nạp router, React + TypeScript + Vite, /health, CI (ruff, pytest, tsc, build), AGENTS.md, CODEOWNERS, mẫu PR, bảo vệ nhánh main
- **Yêu cầu / mục đề cương:** mục 7.1–7.2
- **Vòng:** 1 (M)
- **Phụ thuộc:** —
- **Giờ:** H0–H1
- **Xong khi:** PR đầu tiên chạy CI xanh; 4 máy clone về chạy được bằng một lệnh
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-01-<mô-tả>` · commit bắt đầu bằng `C2-01:`

## C2-02

- **Thẻ việc:** Schema cây app/models/schemas/tree.py (Node, Edge, Rubric, TreeVersion); nạp cây mẫu CTDL&GT do Quyền soạn; GET /classes/{id}/tree
- **Yêu cầu / mục đề cương:** FR-SK-04; mục 5.2.5
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-01
- **Giờ:** H0–H1
- **Xong khi:** Đăng và Thắng lấy được cây mẫu qua API
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-02-<mô-tả>` · commit bắt đầu bằng `C2-02:`

## C2-03

- **Thẻ việc:** Docker Compose đủ dịch vụ theo Bảng 5.15: nginx, api (uvicorn × 4), worker (hàng đợi documents, aggregation, matching, ai), beat, postgres 16 + pgvector, redis, minio, stt (tùy chọn)
- **Yêu cầu / mục đề cương:** mục 5.7; Bảng 5.15
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-01
- **Giờ:** H1–H2
- **Xong khi:** docker compose up chạy đủ dịch vụ trên máy mới
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-03-<mô-tả>` · commit bắt đầu bằng `C2-03:`

## C2-04

- **Thẻ việc:** CI/CD: GitHub Actions chạy test, build image, deploy lên VM qua SSH; Nginx TLS và nâng cấp WebSocket; log JSON tập trung; theo dõi uptime
- **Yêu cầu / mục đề cương:** mục 5.7, 7.1; NFR-07, NFR-10
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-03
- **Giờ:** H2–H3
- **Xong khi:** Merge main thì bản mới tự lên VM; URL HTTPS trả /health
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-04-<mô-tả>` · commit bắt đầu bằng `C2-04:`

## C2-05

- **Thẻ việc:** Bus sự kiện Redis Pub/Sub và schema mastery.py (MasteryChanged)
- **Yêu cầu / mục đề cương:** mục 5.1.3
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-03
- **Giờ:** H3
- **Xong khi:** Test: phát sự kiện thì handler nhận đúng payload
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-05-<mô-tả>` · commit bắt đầu bằng `C2-05:`

## C2-06

- **Thẻ việc:** CSDL và migration Alembic theo danh sách bảng 5.2.3, từ điển dữ liệu 5.2.4, ràng buộc DAG 5.2.5, ma trận thành thạo 5.2.6
- **Yêu cầu / mục đề cương:** mục 5.2
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-03
- **Giờ:** H3–H4
- **Xong khi:** Migration chạy sạch trên máy mới
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-06-<mô-tả>` · commit bắt đầu bằng `C2-06:`

## C2-07

- **Thẻ việc:** Xác thực và phân quyền: đăng nhập, đăng xuất, quên mật khẩu, cập nhật hồ sơ, GET /me; JWT 30 phút; Argon2 hoặc bcrypt; vai GV, SV, QTV; kiểm quyền ở mọi API
- **Yêu cầu / mục đề cương:** FR-AD-01, FR-AD-02; NFR-07, NFR-08; mục 5.6.1
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-06
- **Giờ:** H4–H5
- **Xong khi:** Tài khoản SV gọi API của GV bị 403; token hết hạn sau 30 phút
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-07-<mô-tả>` · commit bắt đầu bằng `C2-07:`

## C2-08

- **Thẻ việc:** Lớp học phần, mã tham gia 8 ký tự, SV tham gia lớp; tải giáo trình PDF/DOCX ≤ 20 MB lên MinIO (kiểm tra định dạng, dung lượng); tạo job và kênh job:{jobId}
- **Yêu cầu / mục đề cương:** FR-SK-01, FR-SK-02, FR-SK-03, FR-TB-01
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-07
- **Giờ:** H5–H6
- **Xong khi:** Tệp sai định dạng hoặc quá 20 MB bị từ chối có thông báo; job trả jobId
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-08-<mô-tả>` · commit bắt đầu bằng `C2-08:`

## C2-09

- **Thẻ việc:** API cây theo Bảng 5.10: thêm, sửa nút; thêm cạnh có kiểm tra chu trình và trả đường đi; xóa cạnh; sửa và duyệt rubric; hậu xử lý DAG bằng NetworkX (phá chu trình, rút gọn bắc cầu); phát hành
- **Yêu cầu / mục đề cương:** FR-SK-04, 06, 07, 08, 09; mục 6.1.4
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-06
- **Giờ:** H6–H7
- **Xong khi:** Thêm cạnh tạo chu trình bị từ chối kèm đường đi; phát hành tạo phiên bản cây
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-09-<mô-tả>` · commit bắt đầu bằng `C2-09:`

## C2-10

- **Thẻ việc:** MasteryService: phát hành thì khởi tạo hoặc di chuyển trạng thái SV sang phiên bản mới; nhận session.completed thì cập nhật theo 4.5.1 và phát mastery.changed; GET /classes/{id}/my-map
- **Yêu cầu / mục đề cương:** FR-SK-09, FR-TB-01; mục 4.5.1, 5.2.6
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-05, C2-09
- **Giờ:** H7–H8
- **Xong khi:** Kết quả Đạt mở khóa nút kế tiếp; phát hành phiên bản mới vẫn giữ trạng thái cũ
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-10-<mô-tả>` · commit bắt đầu bằng `C2-10:`

## C2-11

- **Thẻ việc:** Tổng hợp bản đồ nhiệt (hàng đợi aggregation): tỉ lệ Đạt trên số đã thử, cỡ mẫu tối thiểu, phân màu theo 6.5.2, tách “chưa đủ mẫu” với “chưa đạt”
- **Yêu cầu / mục đề cương:** FR-HM-01, FR-HM-04; mục 6.5.1–6.5.2
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-10
- **Giờ:** H8–H9
- **Xong khi:** Dữ liệu giả lập 30 SV ra đúng màu theo quy tắc
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-11-<mô-tả>` · commit bắt đầu bằng `C2-11:`

## C2-12

- **Thẻ việc:** Truy vết điểm nghẽn gốc (6.5.3) và cảnh báo “Nên giảng lại X”
- **Yêu cầu / mục đề cương:** FR-HM-05; mục 6.5.3–6.5.4
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-11
- **Giờ:** H9–H10
- **Xong khi:** Ví dụ ở mục 6.5 cho đúng nút gốc
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-12-<mô-tả>` · commit bắt đầu bằng `C2-12:`

## C2-13

- **Thẻ việc:** WebSocket class:{id}:heatmap (cell, node, alert); GET /classes/{id}/heatmap (cây và lưới có tên); GET /classes/{id}/nodes/{n}/detail
- **Yêu cầu / mục đề cương:** FR-HM-02, 03, 06; NFR-03; Bảng 5.11
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-11
- **Giờ:** H10–H11
- **Xong khi:** GV thấy ô đổi màu trong ≤ 3 giây (MT5)
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-13-<mô-tả>` · commit bắt đầu bằng `C2-13:`

## C2-14

- **Thẻ việc:** Ghép cặp: bật/tắt tham gia; trọng số bù trừ hai chiều (6.6.2); max_weight_matching; chạy theo lệnh GV và định kỳ bằng Celery beat; gợi ý hạn 48 giờ (beat cho hết hạn); chấp nhận, từ chối, “Đã học cùng”; xác nhận lại qua phiên của Đăng
- **Yêu cầu / mục đề cương:** FR-PM-01, 02, 03, 05, 06, 07; mục 6.6
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-10, C1-07
- **Giờ:** H11–H13
- **Xong khi:** Ví dụ 6.6.4 ra đúng cặp; gợi ý quá 48 giờ tự hết hạn; xác nhận lại Đạt thì cặp chuyển “đã xác nhận”
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-14-<mô-tả>` · commit bắt đầu bằng `C2-14:`

## C2-15

- **Thẻ việc:** Ưu tiên nút đang nghẽn khi ghép; GV điều chỉnh cặp thủ công và xem thống kê hiệu quả (6.6.6)
- **Yêu cầu / mục đề cương:** FR-PM-04, FR-PM-08
- **Vòng:** 2 (S)
- **Phụ thuộc:** C2-12, C2-14
- **Giờ:** H13–H14
- **Xong khi:** “Ghép cặp ưu tiên N5” chọn đúng cặp có nút N5; thống kê hiện tỉ lệ cặp được xác nhận
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-15-<mô-tả>` · commit bắt đầu bằng `C2-15:`

## C2-16

- **Thẻ việc:** Quản lý phiên bản cây: lịch sử, so sánh, khôi phục
- **Yêu cầu / mục đề cương:** FR-SK-10; mục 4.5.3
- **Vòng:** 2 (S)
- **Phụ thuộc:** C2-09
- **Giờ:** H14–H15
- **Xong khi:** Khôi phục phiên bản cũ thành bản nháp mới
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-16-<mô-tả>` · commit bắt đầu bằng `C2-16:`

## C2-17

- **Thẻ việc:** Hồ sơ năng lực SV kèm transcript và ghi âm (GET /classes/{id}/students/{s}/profile); cấu hình ngưỡng (PUT /classes/{id}/settings); lọc, tìm theo tên, chế độ trình chiếu; ghi âm lưu có thời hạn 30 ngày, beat dọn ghi âm quá hạn
- **Yêu cầu / mục đề cương:** FR-HM-07, 08, 09; NFR-09; mục 5.6.2
- **Vòng:** 2 (S)
- **Phụ thuộc:** C2-13, C1-12
- **Giờ:** H15–H16
- **Xong khi:** Đổi ngưỡng thì màu đổi theo; ghi âm quá hạn bị xóa
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-17-<mô-tả>` · commit bắt đầu bằng `C2-17:`

## C2-18

- **Thẻ việc:** Quản trị: quản lý tài khoản, nhập danh sách SV từ CSV; danh mục môn học; hạn mức token và phút ghi âm theo lớp, theo SV; nhật ký và xử lý cờ vi phạm (GET /admin/flags)
- **Yêu cầu / mục đề cương:** FR-AD-03, 04, 06, 07
- **Vòng:** 2 (S)
- **Phụ thuộc:** C2-07
- **Giờ:** H16–H17
- **Xong khi:** Nhập CSV 30 SV thành công; vượt hạn mức thì phiên bị chặn có thông báo
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-18-<mô-tả>` · commit bắt đầu bằng `C2-18:`

## C2-19

- **Thẻ việc:** Thông báo trong ứng dụng (kênh user:{id}) và email
- **Yêu cầu / mục đề cương:** FR-AD-08; Bảng 5.11
- **Vòng:** 2 (S)
- **Phụ thuộc:** C2-07
- **Giờ:** H17–H18
- **Xong khi:** Gợi ý ghép cặp mới tạo thông báo trong ứng dụng và email
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-19-<mô-tả>` · commit bắt đầu bằng `C2-19:`

## C2-20

- **Thẻ việc:** Lịch sử phiên của SV và nghe lại ghi âm; xuất báo cáo lớp CSV/PDF
- **Yêu cầu / mục đề cương:** FR-TB-15, FR-HM-10
- **Vòng:** 3 (C)
- **Phụ thuộc:** C2-17
- **Giờ:** H18–H19
- **Xong khi:** SV nghe lại được ghi âm của mình; file CSV và PDF mở đúng số liệu
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-20-<mô-tả>` · commit bắt đầu bằng `C2-20:`

## C2-21

- **Thẻ việc:** Gác merge main, theo dõi CI và bản deploy, rà soát mã (NFR-14), sửa bug P0/P1; gắn tag khóa code ở H20
- **Yêu cầu / mục đề cương:** —
- **Vòng:** —
- **Phụ thuộc:** —
- **Giờ:** Song song H13–H20
- **Xong khi:** Bản deploy luôn chạy được; không còn bug P0 nào mở ở H19
- **Người phụ trách:** Long
- **Nhánh:** `feat/c2-21-<mô-tả>` · commit bắt đầu bằng `C2-21:`
