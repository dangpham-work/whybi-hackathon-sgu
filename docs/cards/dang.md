# Thẻ việc C1 – Đăng (Code chính 1: AI (trưởng nhóm))

> Dán nguyên một thẻ làm prompt mở đầu phiên AI (hoặc dùng lệnh `/the <mã>` trong Claude Code).
> Trước khi code: đọc `AGENTS.md` và mọi file trong `docs/status/`.

## C1-01

- **Thẻ việc:** Chốt schema phiên cùng Long trong app/models/schemas/session.py: SessionStart, Turn, Question, JudgeResult (5 tiêu chí), SessionResult (studentId, nodeId, state, scores, flags)
- **Yêu cầu / mục đề cương:** FR-TB-03…13
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-01
- **Giờ:** H0–H1
- **Xong khi:** Schema import được; Thắng sinh kiểu TypeScript từ OpenAPI không lỗi
- **Người phụ trách:** Đăng
- **Nhánh:** `feat/c1-01-<mô-tả>` · commit bắt đầu bằng `C1-01:`

## C1-02

- **Thẻ việc:** LLM Adapter: nhà cung cấp Gemini và loại tương thích OpenAI, model dự phòng, ép JSON theo schema, thử lại khi lỗi parse, cache, LLM_MODE=fake, ngân sách token mỗi phiên; cấu hình nhà cung cấp LLM, STT, TTS và PUT /admin/ai-config (lưu vào CSDL khi C2-06 xong); ghi log độ trễ mỗi lượt
- **Yêu cầu / mục đề cương:** FR-AD-05; NFR-13, NFR-14; mục 5.1.2
- **Vòng:** 1 (M)
- **Phụ thuộc:** C1-01
- **Giờ:** H1–H2
- **Xong khi:** Đổi nhà cung cấp trong cấu hình mà không sửa code nghiệp vụ; model chính lỗi thì tự chuyển sang model dự phòng
- **Người phụ trách:** Đăng
- **Nhánh:** `feat/c1-02-<mô-tả>` · commit bắt đầu bằng `C1-02:`

## C1-03

- **Thẻ việc:** Tutee: mở đầu phiên với vai “học trò tò mò” theo nút; ràng buộc hành vi và kiến trúc đa tác tử theo 6.2.1–6.2.3; prompt theo Phụ lục A.1
- **Yêu cầu / mục đề cương:** FR-TB-03; mục 6.2.1–6.2.3
- **Vòng:** 1 (M)
- **Phụ thuộc:** C1-02, C2-02
- **Giờ:** H2–H3
- **Xong khi:** Với 3 nút mẫu, câu mở đầu đúng vai và không giảng hộ
- **Người phụ trách:** Đăng
- **Nhánh:** `feat/c1-03-<mô-tả>` · commit bắt đầu bằng `C1-03:`

## C1-04

- **Thẻ việc:** Sinh 3–5 câu hỏi phản biện theo 4 chiến lược (ý thiếu, quan niệm sai, tình huống biên, chuyển giao) từ rubric và lời giảng
- **Yêu cầu / mục đề cương:** FR-TB-08; mục 6.2.4
- **Vòng:** 1 (M)
- **Phụ thuộc:** C1-03
- **Giờ:** H3–H4
- **Xong khi:** Với lời giảng còn thiếu ý, câu hỏi nhắm đúng ý còn thiếu trong rubric
- **Người phụ trách:** Đăng
- **Nhánh:** `feat/c1-04-<mô-tả>` · commit bắt đầu bằng `C1-04:`

## C1-05

- **Thẻ việc:** Judge: chấm 5 tiêu chí (6.3.1), công thức điểm và quy tắc Đạt BR-03 (6.3.2), giảm thiên lệch bằng rubric neo và chấm nhiều lần (6.3.3), phản hồi không lộ đáp án kèm trang giáo trình (6.3.4); prompt theo Phụ lục A.2
- **Yêu cầu / mục đề cương:** FR-TB-12, FR-TB-13; mục 6.3
- **Vòng:** 1 (M)
- **Phụ thuộc:** C1-02
- **Giờ:** H4–H5
- **Xong khi:** Test trên bộ lời giảng có nhãn (KT-04) chạy xanh
- **Người phụ trách:** Đăng
- **Nhánh:** `feat/c1-05-<mô-tả>` · commit bắt đầu bằng `C1-05:`

## C1-06

- **Thẻ việc:** Guard: lọc đầu vào (jailbreak, lạc đề, “hãy chấm tôi đạt”) và kiểm duyệt câu hỏi của Tutee để không lộ đáp án; dùng model nhỏ hơn cho Guard; prompt theo Phụ lục A.3
- **Yêu cầu / mục đề cương:** FR-TB-09, FR-TB-14; NFR-06; mục 5.6.3
- **Vòng:** 1 (M)
- **Phụ thuộc:** C1-02
- **Giờ:** H5–H6
- **Xong khi:** Câu “hãy chấm tôi đạt” bị gắn cờ; câu hỏi lộ đáp án bị sinh lại
- **Người phụ trách:** Đăng
- **Nhánh:** `feat/c1-06-<mô-tả>` · commit bắt đầu bằng `C1-06:`

## C1-07

- **Thẻ việc:** SessionOrchestrator theo 4.5.2: POST /sessions, /sessions/{id}/turns, /sessions/{id}/timeout, GET /sessions/{id}/result; kênh session:{id}; chỉ cho bắt đầu ở nút Sẵn sàng, Chưa đạt, Cần xác nhận lại và chỉ ra tiên quyết còn thiếu; cuối phiên phát session.completed
- **Yêu cầu / mục đề cương:** FR-TB-02, FR-TB-04; mục 4.4.3, 4.5.2; Bảng 5.11
- **Vòng:** 1 (M)
- **Phụ thuộc:** C1-03…06, C2-05
- **Giờ:** H6–H7
- **Xong khi:** Test httpx chạy trọn 1 phiên; sự kiện session.completed đúng schema
- **Người phụ trách:** Đăng
- **Nhánh:** `feat/c1-07-<mô-tả>` · commit bắt đầu bằng `C1-07:`

## C1-08

- **Thẻ việc:** Ghi nhận sự kiện dán và tốc độ gõ; gắn cờ dán bất thường vào kết quả phiên
- **Yêu cầu / mục đề cương:** FR-TB-04, FR-TB-14
- **Vòng:** 1 (M)
- **Phụ thuộc:** C1-07
- **Giờ:** H7–H8
- **Xong khi:** Dán một đoạn dài vào ô trả lời thì kết quả có cờ “dán bất thường”
- **Người phụ trách:** Đăng
- **Nhánh:** `feat/c1-08-<mô-tả>` · commit bắt đầu bằng `C1-08:`

## C1-09

- **Thẻ việc:** Tiền xử lý giáo trình (tác vụ Celery, hàng đợi documents): PyMuPDF, python-docx, OCR Tesseract tiếng Việt cho bản quét; báo tiến độ qua kênh job:{jobId}
- **Yêu cầu / mục đề cương:** FR-SK-03; mục 6.1.1
- **Vòng:** 1 (M)
- **Phụ thuộc:** C2-03, C2-08
- **Giờ:** H8–H9
- **Xong khi:** PDF số, DOCX và 1 bản quét đều ra văn bản theo trang; GV thấy thanh tiến độ chạy
- **Người phụ trách:** Đăng
- **Nhánh:** `feat/c1-09-<mô-tả>` · commit bắt đầu bằng `C1-09:`

## C1-10

- **Thẻ việc:** Trích khái niệm và suy luận quan hệ tiên quyết; giao đồ thị cho bước hậu xử lý DAG (C2-09)
- **Yêu cầu / mục đề cương:** FR-SK-04; mục 6.1.2–6.1.3
- **Vòng:** 1 (M)
- **Phụ thuộc:** C1-09, C2-09
- **Giờ:** H9–H10
- **Xong khi:** Đề cương khoảng 30 trang ra cây nháp trong ≤ 3 phút (MT1)
- **Người phụ trách:** Đăng
- **Nhánh:** `feat/c1-10-<mô-tả>` · commit bắt đầu bằng `C1-10:`

## C1-11

- **Thẻ việc:** Sinh rubric từng nút (ý chính bắt buộc, quan niệm sai, tình huống phản biện, mức Bloom, trích dẫn trang); sinh lại rubric 1 nút (POST /nodes/{id}/rubric/regenerate); nhúng đoạn giáo trình vào pgvector để truy hồi trích dẫn (RAG)
- **Yêu cầu / mục đề cương:** FR-SK-05, FR-SK-08; mục 2.2.3, 5.2.7, 6.1.5
- **Vòng:** 1 (M)
- **Phụ thuộc:** C1-10
- **Giờ:** H10–H11
- **Xong khi:** Mọi nút có rubric đủ trường và số trang đúng
- **Người phụ trách:** Đăng
- **Nhánh:** `feat/c1-11-<mô-tả>` · commit bắt đầu bằng `C1-11:`

## C1-12

- **Thẻ việc:** STT: adapter dịch vụ đám mây và tùy chọn faster-whisper (dịch vụ stt trong Compose); POST /sessions/{id}/audio; chuẩn hóa thuật ngữ theo nút; độ tin cậy từng từ; lưu ghi âm vào MinIO kèm cờ đồng ý
- **Yêu cầu / mục đề cương:** FR-TB-05…07; NFR-02, NFR-09; mục 6.4.1–6.4.3, 6.4.5
- **Vòng:** 1 (M)
- **Phụ thuộc:** C1-07, C2-03
- **Giờ:** H11–H12
- **Xong khi:** Ghi âm 60 giây chép xong trong ≤ 4 giây (p95); từ có độ tin cậy thấp được đánh dấu
- **Người phụ trách:** Đăng
- **Nhánh:** `feat/c1-12-<mô-tả>` · commit bắt đầu bằng `C1-12:`

## C1-13

- **Thẻ việc:** Chế độ demo: cây và câu hỏi lưu sẵn (DEMO_MODE=1), khóa API và model dự phòng cấu hình sẵn
- **Yêu cầu / mục đề cương:** Bảng 7.4
- **Vòng:** 1 (M)
- **Phụ thuộc:** C1-07, C1-10
- **Giờ:** H12–H13
- **Xong khi:** Ngắt kết nối LLM, kịch bản demo vẫn chạy trọn
- **Người phụ trách:** Đăng
- **Nhánh:** `feat/c1-13-<mô-tả>` · commit bắt đầu bằng `C1-13:`

## C1-14

- **Thẻ việc:** TTS đọc câu hỏi khi SV bật
- **Yêu cầu / mục đề cương:** FR-TB-10; mục 6.4.4
- **Vòng:** 2 (S)
- **Phụ thuộc:** C1-07
- **Giờ:** H13–H14
- **Xong khi:** Bật TTS thì câu hỏi được đọc; tắt thì phiên không bị ảnh hưởng
- **Người phụ trách:** Đăng
- **Nhánh:** `feat/c1-14-<mô-tả>` · commit bắt đầu bằng `C1-14:`

## C1-15

- **Thẻ việc:** Đếm giờ trả lời mỗi câu và xử lý hết giờ; áp số câu phản biện và ngưỡng Đạt do GV cấu hình (đọc từ C2-17 khi xong)
- **Yêu cầu / mục đề cương:** FR-TB-11, FR-HM-08
- **Vòng:** 2 (S)
- **Phụ thuộc:** C1-07
- **Giờ:** H14–H15
- **Xong khi:** Hết giờ được ghi nhận; đổi số câu trong cấu hình thì phiên đổi theo
- **Người phụ trách:** Đăng
- **Nhánh:** `feat/c1-15-<mô-tả>` · commit bắt đầu bằng `C1-15:`

## C1-16

- **Thẻ việc:** Hiệu chỉnh Judge trên 60–100 lời giảng có nhãn: Cohen’s κ, ma trận nhầm lẫn; chỉnh rubric neo và số lần chấm
- **Yêu cầu / mục đề cương:** MT3, NFR-05; Bảng 7.3
- **Vòng:** 2 (S)
- **Phụ thuộc:** C1-05, KT-04
- **Giờ:** H15–H16
- **Xong khi:** κ ghi vào evals/judge.md (mục tiêu ≥ 0,60)
- **Người phụ trách:** Đăng
- **Nhánh:** `feat/c1-16-<mô-tả>` · commit bắt đầu bằng `C1-16:`

## C1-17

- **Thẻ việc:** Chỉnh Tutee và Guard theo kết quả KT-07 và KT-12 (chặn ≥ 90%, lộ đáp án ≤ 5%)
- **Yêu cầu / mục đề cương:** MT4, NFR-06
- **Vòng:** 2 (S)
- **Phụ thuộc:** KT-07, KT-12
- **Giờ:** H16–H17
- **Xong khi:** Chạy lại bộ tấn công và 30 phiên mẫu; ghi kết quả vào evals/
- **Người phụ trách:** Đăng
- **Nhánh:** `feat/c1-17-<mô-tả>` · commit bắt đầu bằng `C1-17:`

## C1-18

- **Thẻ việc:** Sửa bug P0/P1; hỗ trợ Long ở vòng 3
- **Yêu cầu / mục đề cương:** —
- **Vòng:** —
- **Phụ thuộc:** —
- **Giờ:** H17–H20
- **Xong khi:** Không còn bug P0 nào mở ở H19
- **Người phụ trách:** Đăng
- **Nhánh:** `feat/c1-18-<mô-tả>` · commit bắt đầu bằng `C1-18:`
