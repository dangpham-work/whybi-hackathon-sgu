# Kết quả đánh giá – chi phí AI mỗi phiên (tiêu chí VI)

- Ngày chạy: 2026-11-07 · Công cụ: `evals/cost.py` · LLM_MODE=real, gọi API thật
- Luồng: câu mở đầu → mỗi lượt SV (Guard đầu vào → bao phủ → câu hỏi + Guard đầu ra) → Judge 2 lần chấm; 3 câu phản biện; lời SV lấy từ `evals/tutee/sessions.jsonl`
- Giá: bậc Standard trả phí, tra ngày 2026-11-07 (OpenAI, Google AI Studio). Quy đổi 26.000 đ/USD (giả định làm tròn).

## Tổng hợp

| Model | Phiên đo | Lời gọi LLM / phiên | Token vào / phiên | Token ra / phiên | Token tối đa / ngân sách | Chi phí / phiên | Thời gian AI / phiên |
|---|---|---|---|---|---|---|---|
| `gpt-4o-mini` | 6/6 | 19.0 | 13,206 | 1,269 | 19,577 / 20,000 | **$0.0027** (≈ 71 đ) | 67.8s |
| `gemini-3.5-flash-lite` | 3/6 | 21.7 | 10,149 | 1,901 | 13,182 / 20,000 | **$0.0078** (≈ 203 đ) | 136.0s |

## Chi phí theo bước (trung bình mỗi phiên)

**`gpt-4o-mini`**

| Bước | Lời gọi | Token vào | Token ra | Tỉ trọng chi phí |
|---|---|---|---|---|
| Judge chấm 5 tiêu chí | 2.0 | 3,656 | 799 | 37% |
| Tutee sinh câu (mở đầu + phản biện) | 4.7 | 4,044 | 216 | 27% |
| Tutee phân tích bao phủ | 3.5 | 2,112 | 111 | 14% |
| Guard đầu ra (kiểm lộ đáp án) | 4.8 | 1,838 | 94 | 12% |
| Guard đầu vào (LLM, khi luật không quyết được) | 4.0 | 1,556 | 50 | 10% |

Lời gọi không thành công (đã tính token nếu có): 2 – error:TransientProviderError

**`gemini-3.5-flash-lite`**

| Bước | Lời gọi | Token vào | Token ra | Tỉ trọng chi phí |
|---|---|---|---|---|
| Judge chấm 5 tiêu chí | 2.7 | 2,586 | 1,274 | 51% |
| Tutee sinh câu (mở đầu + phản biện) | 6.0 | 3,354 | 305 | 23% |
| Tutee phân tích bao phủ | 4.3 | 1,742 | 185 | 13% |
| Guard đầu ra (kiểm lộ đáp án) | 4.7 | 1,349 | 88 | 8% |
| Guard đầu vào (LLM, khi luật không quyết được) | 4.0 | 1,117 | 49 | 6% |

Lời gọi không thành công (đã tính token nếu có): 7 – error:TransientProviderError

## Phiên lỗi

- `gemini-3.5-flash-lite` T01: AppError: Dịch vụ AI tạm thời không khả dụng
- `gemini-3.5-flash-lite` T16: AppError: Dịch vụ AI tạm thời không khả dụng
- `gemini-3.5-flash-lite` T26: AppError: Dịch vụ AI tạm thời không khả dụng

<!-- phan-tich: phần dưới viết tay, cost.py giữ nguyên khi đo lại -->

## Phân tích

### Chi phí khi dùng thật (model chính `gpt-4o-mini`)

| Quy mô | Số phiên | Chi phí LLM |
|---|---|---|
| 1 SV học hết cây CTDL&GT (11 nút, trung bình 2 lần thử / nút) | 22 | ≈ $0,06 (≈ 1.550 đ) |
| 1 lớp 40 SV, một học kỳ | 880 | ≈ $2,4 (≈ 62.000 đ) |
| 10 lớp (400 SV), một học kỳ | 8.800 | ≈ $24 (≈ 620.000 đ) |

Ước tính = chi phí trung bình mỗi phiên đo được × số phiên. Chưa gồm STT (giọng nói) và embedding cho RAG;
hai phần này không có trong luồng đo (SV gõ chữ, cây mẫu không có tài liệu tải lên).

Hạ tầng: máy chủ EC2 t3.small (Sydney), ổ đĩa và IP công khai khoảng **$19/tháng** (ước tính theo giá on-demand),
trừ vào credit AWS. Một máy đủ cho demo và một lớp; chi phí LLM nhỏ hơn hạ tầng nhiều lần.

### Vì sao chọn `gpt-4o-mini` làm model chính, Gemini làm dự phòng

- Rẻ hơn **≈ 2,9 lần** mỗi phiên ($0,0027 so với $0,0078). Gemini 3.5 Flash-Lite đọc ít token vào hơn
  nhưng token ra đắt gấp 4 lần ($2,50 so với $0,60 / 1M), và Judge của Gemini ra dài hơn (1.274 so với 799 token).
- Nhanh hơn: trung bình 68 s so với 136 s tổng thời gian AI mỗi phiên (≈ 3–5 s mỗi lượt hỏi).
- Khóa Gemini đang ở **bậc miễn phí, giới hạn 15 lời gọi / phút**: 3/6 phiên đo bị lỗi 429, vì một phiên cần ~20 lời gọi.
  Bậc miễn phí chỉ dùng được làm dự phòng khi OpenAI lỗi, không đủ làm model chính cho nhiều SV cùng lúc.
  Muốn dùng Gemini làm chính phải bật bậc trả phí (credit GCP).

### Cơ chế tiết kiệm đã có trong code

| Cơ chế | Ở đâu | Tác dụng |
|---|---|---|
| Ngân sách token mỗi phiên (NFR-13) | `gateway.py` `_check_budget`, `LLM_SESSION_TOKEN_BUDGET` | Chặn phiên tiêu quá mức (vòng lặp, SV spam) |
| Cache kết quả (temperature = 0) | `gateway.py` `call_json` | Guard, bao phủ, Judge gặp lại đầu vào cũ thì không gọi lại |
| Model nhỏ cho Guard | `LLM_GUARD_MODEL` | Bước gọi nhiều nhất dùng model rẻ nhất |
| Chiến lược hỏi do code chọn | `tutee.py` `choose_strategy` | LLM chỉ diễn đạt câu hỏi, không phải suy luận cả phiên |
| Kiểm lộ đáp án bằng luật trước | `guard.py` `leaked_point` | Câu lộ rõ bị chặn không tốn lời gọi LLM |
| Model dự phòng + thử lại có giới hạn | `gateway.py` | Lỗi nhà cung cấp không làm hỏng phiên, không thử lại vô hạn |
| `LLM_MODE=fake` | CI, test, kiểm thử tải | Toàn bộ test và CI không tốn tiền API |
| `DEMO_MODE=1` | `app/ai/demo.py` | Mất mạng thì dùng nội dung lưu sẵn, demo không phụ thuộc API |

### Rủi ro phát hiện khi đo

- **Ngân sách 20.000 token sát giới hạn:** phiên dài nhất dùng 19.577 token (bản chạy thử trước đó 19.939).
  Phiên SV giảng dài hoặc Guard phải sinh lại câu hỏi nhiều lần có thể hết ngân sách trước bước Judge.
  Đề xuất: nâng `LLM_SESSION_TOKEN_BUDGET` lên 30.000 (với tỉ lệ token vào/ra đo được, chi phí một phiên dùng hết ngân sách ≈ $0,006),
  hoặc chừa riêng phần cho Judge.
- Tutee sinh câu 4,7 lần / phiên cho 4 câu cần thiết: thỉnh thoảng Guard đầu ra bắt lộ và cho sinh lại. Đây là chi phí
  của an toàn, chấp nhận được (27% chi phí).
- Judge chiếm phần lớn nhất (37%) vì chấm 2 lần để ổn định. Giảm còn 1 lần tiết kiệm ≈ 18% nhưng phải đo lại κ.
