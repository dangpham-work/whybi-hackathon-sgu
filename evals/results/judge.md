# Kết quả đánh giá – judge

- Ngày chạy: 2026-11-05 · Commit: 9f31a38 · Người chạy: long
- Cấu hình: LLM_MODE=fake (semantic fallback) · dữ liệu=`evals/judge/` (62 mẫu)

| Chỉ số | Chỉ tiêu (Bảng 7.3) | Kết quả |
|---|---|---|
| Cohen's κ (1 lần chấm) | ≥ 0.60 | 0.643 – ĐẠT |
| Cohen's κ (2 lần chấm) | ≥ 0.60 | 0.643 – ĐẠT |
| Cohen's κ (3 lần chấm) | ≥ 0.60 | 0.643 – ĐẠT |

## Nhận xét / lỗi điển hình

- 1 lần chấm – ma trận nhầm lẫn:

| thật \ Judge | PASSED | FAILED |
|---|---|---|
| PASSED | 22 | 8 |
| FAILED | 3 | 29 |
- 1 lần chấm – MAE tiêu chí: CORRECTNESS 19.7, COVERAGE 17.5, ESSENCE 15.8, ROBUSTNESS 53.8, CLARITY 16.8
- 2 lần chấm – ma trận nhầm lẫn:

| thật \ Judge | PASSED | FAILED |
|---|---|---|
| PASSED | 22 | 8 |
| FAILED | 3 | 29 |
- 2 lần chấm – MAE tiêu chí: CORRECTNESS 19.7, COVERAGE 17.5, ESSENCE 15.8, ROBUSTNESS 53.8, CLARITY 16.8
- 3 lần chấm – ma trận nhầm lẫn:

| thật \ Judge | PASSED | FAILED |
|---|---|---|
| PASSED | 22 | 8 |
| FAILED | 3 | 29 |
- 3 lần chấm – MAE tiêu chí: CORRECTNESS 19.7, COVERAGE 17.5, ESSENCE 15.8, ROBUSTNESS 53.8, CLARITY 16.8
- Số lần chấm tốt nhất: 1 (κ = 0.643).
