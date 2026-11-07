# Kết quả đánh giá – tutee

- Ngày chạy: 2026-11-05 · Commit: 99f5097 · Người chạy: Đăng & Quyền
- Cấu hình: TuteeAgent + GuardAgent (C1-17, KT-12) · dữ liệu=`evals/tutee/` (30 phiên, 120 câu hỏi)

| Chỉ số | Chỉ tiêu (Bảng 7.3) | Kết quả |
|---|---|---|
| Tỉ lệ câu hỏi lộ đáp án | ≤ 5% | 1.7% (2/120) – ĐẠT |
| Sai luật vai (Phụ lục A.1) | 0 | 0/120 – ĐẠT |
| Guard đầu ra bắt câu lộ (recall) | — | 100.0% (2/2) |
| Guard chặn nhầm câu sạch | — | 0.0% (0/118) |

## Nhận xét / lỗi điển hình

- 30 phiên mẫu T01–T30 (6 nhóm kịch bản: correct, missing_point, misconception, edge_case, transfer, answer_request) qua TuteeAgent đạt chuẩn vai học trò (xưng hô "mình" - "bạn", không giảng hộ hay tự đưa đáp án).
- 2 câu hỏi lộ đáp án do người chấm độc lập ghi nhận (T15 câu 2 và T22 câu 3) đều được GuardAgent nhận diện và chặn thành công ở đầu ra (recall 100%), kích hoạt cơ chế sinh lại / câu hỏi dự phòng.
- 118 câu hỏi sạch đều qua Guard thuận lợi (tỉ lệ chặn nhầm 0.0%).
