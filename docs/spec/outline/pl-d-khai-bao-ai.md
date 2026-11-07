# PHỤ LỤC D. KHAI BÁO SỬ DỤNG CÔNG CỤ AI

*Bảng D.1. Khai báo công cụ AI đã sử dụng trong quá trình thực hiện dự án*

| Công cụ | Phiên bản | Mục đích sử dụng | Phần liên quan |
|---|---|---|---|
| Claude (Anthropic) | Claude 3.5 Sonnet / Claude Code | Hỗ trợ lập khung đề cương, gợi ý cấu trúc tài liệu, rà soát logic kiến trúc và soạn mã PlantUML cho hệ thống sơ đồ thiết kế | Toàn bộ đề cương (Chương 1–7); Phụ lục E |
| Gemini (Google) | Gemini 2.5 Flash / 2.5 Flash Lite | Mô hình ngôn ngữ lớn làm backend cho LLMGateway: trích xuất cây kỹ năng (MX1), Tutee phản biện gợi mở (MX2), Judge chấm rubric 5 tiêu chí (MX2) và Guard phân loại an toàn | Chương 4, 5, 6, 7; Phụ lục A, B, C |
| Whisper (OpenAI) | Whisper Large v3 / Faster-Whisper | Nhận dạng giọng nói tiếng Việt (STT) tích hợp trong SpeechService, hỗ trợ sinh viên giảng giải bằng giọng nói và trích xuất thuật ngữ | Chương 5, 6, 7 (MX2); Phụ lục A |
| GitHub Copilot & Cursor | Bản cập nhật 2026 | Hỗ trợ lập trình theo cặp (pair programming), scaffold giao diện React/Tailwind, viết bộ kiểm thử tự động (pytest, vitest, Playwright) | Toàn bộ mã nguồn backend, frontend và e2e |

### Cam kết về tính trung thực và trách nhiệm học thuật:
1. **Kiểm soát con người:** Mọi ý tưởng kiến trúc (4 mắt xích MX1–MX4, mô hình "Sinh viên làm thầy, AI làm học trò"), thiết kế luồng dữ liệu, rubric đánh giá sư phạm BR-03 và thuật toán ghép cặp đều do đội ngũ phát triển (WhyBloom) tự thiết kế và quyết định.
2. **Kiểm chứng độc lập:** Các đoạn mã và nội dung do công cụ AI hỗ trợ sinh ra đều được thành viên trong nhóm rà soát, viết bài kiểm thử bao phủ (100% test pass trên CI) và hiệu chỉnh thủ công để đảm bảo tính an toàn, bảo mật và chính xác kỹ thuật.
3. **Không sao chép trái phép:** Không sử dụng AI để tạo văn bản ngụy tạo số liệu hoặc vi phạm bản quyền của bất kỳ bên thứ ba nào.
