# Tác tử AI

> Gốc: chương 6 – [outline/06-ai-thuat-toan.md](outline/06-ai-thuat-toan.md); prompt: [outline/pl-a-prompt.md](outline/pl-a-prompt.md);
> đánh giá: mục 7.4 – [outline/07-cai-dat-kiem-thu.md](outline/07-cai-dat-kiem-thu.md); chống gian lận: [Phụ lục B](outline/pl-b-chong-gian-lan.md).

| Thành phần | File | Thẻ |
|---|---|---|
| LLM Gateway (Gemini / tương thích OpenAI / fake, dự phòng, cache, ngân sách token) | `backend/app/ai/gateway.py`, `ai/providers/` | C1-02 |
| Tutee – học trò tò mò, hỏi phản biện (6.2) | `ai/agents/tutee.py`, `ai/prompts/tutee.md` | C1-03, C1-04, C1-17 |
| Judge – chấm 5 tiêu chí, quy tắc Đạt BR-03 (6.3) | `ai/agents/judge.py`, `ai/prompts/judge.md` | C1-05, C1-16 |
| Guard – kiểm duyệt đầu vào / đầu ra (5.6.3) | `ai/agents/guard.py`, `ai/prompts/guard_input.md` | C1-06, C1-17 |
| Trích cây + rubric + pgvector (6.1) | `workers/documents.py`, `services/` | C1-09…C1-11 |
| STT / TTS (6.4) | `ai/providers/`, dịch vụ `stt` (profile `stt`) | C1-12, C1-14 |

- `LLM_MODE=fake`: gateway trả JSON mẫu đúng schema – frontend và test chạy không cần khóa API.
- `DEMO_MODE=1`: dùng cây và câu hỏi lưu sẵn cho kịch bản demo (C1-13).
- Bộ đánh giá: `evals/` (Quyền, KT-04, KT-07, KT-10, KT-12).
