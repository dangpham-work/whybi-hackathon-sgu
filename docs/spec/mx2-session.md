# MX2 – Giảng lại cho AI

> Bản tóm lược để làm việc. Nội dung gốc: [đề cương](README.md). Đổi hợp đồng ⇒ báo trong `docs/status/`.

## Yêu cầu chức năng

| Mã | Yêu cầu | Tác nhân | Ưu tiên |
|---|---|---|---|
| FR-TB-01 | Tham gia lớp bằng mã; xem bản đồ học tập cá nhân dạng cây với trạng thái từng nút | SV | M |
| FR-TB-02 | Chỉ cho phép bắt đầu phiên ở nút Sẵn sàng / Chưa đạt / Cần xác nhận lại; chỉ ra tiên quyết còn thiếu | Hệ thống | M |
| FR-TB-03 | AI mở đầu phiên với vai “học trò tò mò”, nhờ SV giảng khái niệm | Hệ thống | M |
| FR-TB-04 | Nhập lời giảng và câu trả lời bằng văn bản; ghi nhận sự kiện dán và tốc độ gõ | SV | M |
| FR-TB-05 | Nhập bằng giọng nói: ghi âm ≤ 3 phút, hiển thị dạng sóng, ghi lại, dừng | SV | M |
| FR-TB-06 | Chuyển giọng nói thành văn bản tiếng Việt, chuẩn hóa thuật ngữ của nút | Hệ thống | M |
| FR-TB-07 | Khi độ tin cậy STT thấp: hiển thị bản chép lời, gạch chân từ không chắc, cho SV chỉnh nhỏ; ghi nhận chỉnh sửa | SV, Hệ thống | M |
| FR-TB-08 | Sinh 3–5 câu hỏi phản biện theo chiến lược (ý thiếu, quan niệm sai, tình huống biên, chuyển giao) | Hệ thống | M |
| FR-TB-09 | Không giảng hộ, không lộ đáp án trong câu hỏi (kiểm duyệt đầu ra) | Hệ thống | M |
| FR-TB-10 | Đọc câu hỏi bằng giọng nói (TTS) khi SV bật | SV | S |
| FR-TB-11 | Đếm giờ trả lời mỗi câu; ghi nhận hết giờ | Hệ thống | S |
| FR-TB-12 | Chấm theo 5 tiêu chí bằng tác tử chấm độc lập; áp dụng quy tắc Đạt (BR-03) | Hệ thống | M |
| FR-TB-13 | Hiển thị kết quả: điểm từng tiêu chí, điểm mạnh, gợi ý ôn dạng câu hỏi gợi mở, trang giáo trình | SV | M |
| FR-TB-14 | Phát hiện và gắn cờ jailbreak / lạc đề / dán bất thường | Hệ thống | M |
| FR-TB-15 | Xem lịch sử phiên của bản thân, nghe lại ghi âm | SV | C |

## Đọc thêm trong đề cương

- 3.3.2 – [03-yeu-cau](outline/03-yeu-cau.md)
- 4.3.2, 4.4.3, 4.5.1–4.5.2 – [04-phan-tich](outline/04-phan-tich.md)
- 6.2–6.4 Tác tử, chấm điểm, giọng nói – [06-ai-thuat-toan](outline/06-ai-thuat-toan.md)
- Phụ lục A, B – [prompt](outline/pl-a-prompt.md), [chống gian lận](outline/pl-b-chong-gian-lan.md)

## Vị trí mã

- `backend/app/api/sessions.py`
- `backend/app/ai/ (gateway, agents, prompts)`
- `backend/app/models/session.py`
- `backend/app/models/schemas/session.py`
- `frontend/src/components/Recorder.tsx`
- `frontend/src/pages/student/ (SV-03…SV-06)`

## Thẻ việc liên quan

| Thẻ | Người | Vòng | Nội dung |
|---|---|---|---|
| C1-01 | Đăng | 1 (M) | Chốt schema phiên cùng Long trong app/models/schemas/session.py: SessionStart, Turn, Question, JudgeResult (5 tiêu chí), SessionResult (stud… |
| C1-02 | Đăng | 1 (M) | LLM Adapter: nhà cung cấp Gemini và loại tương thích OpenAI, model dự phòng, ép JSON theo schema, thử lại khi lỗi parse, cache, LLM_MODE=fak… |
| C1-03 | Đăng | 1 (M) | Tutee: mở đầu phiên với vai “học trò tò mò” theo nút; ràng buộc hành vi và kiến trúc đa tác tử theo 6.2.1–6.2.3; prompt theo Phụ lục A.1 |
| C1-04 | Đăng | 1 (M) | Sinh 3–5 câu hỏi phản biện theo 4 chiến lược (ý thiếu, quan niệm sai, tình huống biên, chuyển giao) từ rubric và lời giảng |
| C1-05 | Đăng | 1 (M) | Judge: chấm 5 tiêu chí (6.3.1), công thức điểm và quy tắc Đạt BR-03 (6.3.2), giảm thiên lệch bằng rubric neo và chấm nhiều lần (6.3.3), phản… |
| C1-06 | Đăng | 1 (M) | Guard: lọc đầu vào (jailbreak, lạc đề, “hãy chấm tôi đạt”) và kiểm duyệt câu hỏi của Tutee để không lộ đáp án; dùng model nhỏ hơn cho Guard;… |
| C1-07 | Đăng | 1 (M) | SessionOrchestrator theo 4.5.2: POST /sessions, /sessions/{id}/turns, /sessions/{id}/timeout, GET /sessions/{id}/result; kênh session:{id}; … |
| C1-08 | Đăng | 1 (M) | Ghi nhận sự kiện dán và tốc độ gõ; gắn cờ dán bất thường vào kết quả phiên |
| C1-12 | Đăng | 1 (M) | STT: adapter dịch vụ đám mây và tùy chọn faster-whisper (dịch vụ stt trong Compose); POST /sessions/{id}/audio; chuẩn hóa thuật ngữ theo nút… |
| C1-14 | Đăng | 2 (S) | TTS đọc câu hỏi khi SV bật |
| C1-15 | Đăng | 2 (S) | Đếm giờ trả lời mỗi câu và xử lý hết giờ; áp số câu phản biện và ngưỡng Đạt do GV cấu hình (đọc từ C2-17 khi xong) |
| C1-16 | Đăng | 2 (S) | Hiệu chỉnh Judge trên 60–100 lời giảng có nhãn: Cohen’s κ, ma trận nhầm lẫn; chỉnh rubric neo và số lần chấm |
| C1-17 | Đăng | 2 (S) | Chỉnh Tutee và Guard theo kết quả KT-07 và KT-12 (chặn ≥ 90%, lộ đáp án ≤ 5%) |
| C2-03 | Long | 1 (M) | Docker Compose đủ dịch vụ theo Bảng 5.15: nginx, api (uvicorn × 4), worker (hàng đợi documents, aggregation, matching, ai), beat, postgres 1… |
| C2-08 | Long | 1 (M) | Lớp học phần, mã tham gia 8 ký tự, SV tham gia lớp; tải giáo trình PDF/DOCX ≤ 20 MB lên MinIO (kiểm tra định dạng, dung lượng); tạo job và k… |
| C2-10 | Long | 1 (M) | MasteryService: phát hành thì khởi tạo hoặc di chuyển trạng thái SV sang phiên bản mới; nhận session.completed thì cập nhật theo 4.5.1 và ph… |
| C2-17 | Long | 2 (S) | Hồ sơ năng lực SV kèm transcript và ghi âm (GET /classes/{id}/students/{s}/profile); cấu hình ngưỡng (PUT /classes/{id}/settings); lọc, tìm … |
| C2-18 | Long | 2 (S) | Quản trị: quản lý tài khoản, nhập danh sách SV từ CSV; danh mục môn học; hạn mức token và phút ghi âm theo lớp, theo SV; nhật ký và xử lý cờ… |
| C2-20 | Long | 3 (C) | Lịch sử phiên của SV và nghe lại ghi âm; xuất báo cáo lớp CSV/PDF |
| KT-04 | Quyền | 1 (M) | Nạp các bộ đánh giá đã chuẩn bị vào evals/: 60–100 lời giảng có nhãn, ≥ 50 kịch bản tấn công, 30 đoạn ghi âm, 3–5 cây chuẩn |
| KT-06 | Quyền | 1 (M) | Test chức năng MX2 theo Bảng 7.2 trên bản deploy: vào phiên, mở đầu, phản biện, chấm, kết quả; báo bug |
| KT-07 | Quyền | 1 (M) | Chạy ≥ 50 kịch bản tấn công (Phụ lục B) vào Guard: tỉ lệ chặn, tỉ lệ Đạt sai; ghi vào evals/guard.md |
| KT-08 | Quyền | 1 (M) | Test bảo mật và phân quyền: JWT hết hạn, băm mật khẩu, SV không xem được kết quả của nhau, chỉ GV của lớp xem dữ liệu có tên, đồng ý ghi âm |
| KT-10 | Quyền | 1 (M) | Test giọng nói: 30 đoạn ghi âm, WER, tỉ lệ thuật ngữ đúng, độ trễ STT; luồng ghi âm → xác nhận → gửi |
| KT-12 | Quyền | 2 (S) | Đánh giá Tutee trên 30 phiên mẫu: tỉ lệ câu hỏi lộ đáp án, tỉ lệ câu hỏi qua Guard ngay lần sinh đầu |
| KT-14 | Quyền | 2 (S) | Test vòng 2: phiên bản cây, TTS, đếm giờ, hồ sơ SV, cấu hình, trình chiếu, ưu tiên nút nghẽn, điều chỉnh cặp, quản trị, thông báo; responsiv… |
| KT-15 | Quyền | 3 (C) | Test vòng 3: lịch sử phiên, nghe lại, xuất báo cáo |
| GD-04 | Thắng | 1 (M) | Đăng nhập, quên mật khẩu, hồ sơ; SV-01 Danh sách lớp và nhập mã tham gia |
| GD-06 | Thắng | 1 (M) | SV-02 Bản đồ học tập, SV-03 Chi tiết nút (trạng thái, điểm cao nhất, tiên quyết còn thiếu) |
| GD-07 | Thắng | 1 (M) | SV-04 Phiên giảng lại: hội thoại, ô gõ (gửi sự kiện dán và tốc độ gõ), Recorder và Waveform ghi âm ≤ 3 phút, hỏi đồng ý trước khi ghi |
| GD-08 | Thắng | 1 (M) | SV-05 Xác nhận bản chép lời (gạch chân từ không chắc, cho sửa nhỏ); SV-06 Kết quả và phản hồi |
| GD-12 | Thắng | 2 (S) | SV-04: nút bật TTS và đồng hồ đếm giờ; GV-09: điều chỉnh cặp thủ công và thống kê |
| GD-13 | Thắng | 2 (S) | GV-07 Hồ sơ năng lực SV; GV-08 Transcript, ghi âm, điểm từng tiêu chí, cờ vi phạm |
| GD-16 | Thắng | 3 (C) | SV-08 Lịch sử phiên và nghe lại; nút xuất báo cáo lớp CSV/PDF ở GV-05 |
