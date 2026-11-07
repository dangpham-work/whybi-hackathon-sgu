# KT-07 – đánh giá Guard

Chuyển bộ chạy từ whybi-ai@62802b3; dữ liệu KT-04 gồm 58 kịch bản. AT08–AT58 là nháp AI, cần rà độc lập.

GitHub CI chạy `cd backend && uv run python ../evals/run.py guard --judge --ci-smoke --write` với LLM_MODE=fake và lưu artifact **kt07-guard-report**. Báo cáo chứa commit, chế độ chạy, tỉ lệ chặn, cờ dán, danh sách câu lọt và lỗi. Không dùng số liệu của repo cũ.

`--ci-smoke` chỉ đạt khi >=50 ca chạy không lỗi; báo cáo vẫn ghi **chưa đạt/chưa đủ số liệu** nếu chất lượng chưa được chứng minh. Lệnh mặc định không có cờ này trả mã 1 khi thiếu số liệu hoặc chưa đạt ngưỡng.

Đo model thật: `LLM_MODE=real uv run python ../evals/run.py guard --judge --write`. Cần API key cấu hình riêng; repo mới hiện không có GitHub Actions secrets. Không commit khóa API.

Giới hạn: tỉ lệ chặn chỉ tính ca có kỳ vọng JAILBREAK/OFF_TOPIC; PASTE_SUSPECTED đếm riêng. FakeProvider trả VALID nên phép đo fake chỉ phản ánh bộ lọc luật. Judge fake không dùng tính Đạt sai; `--judge` với model thật hiện chỉ chấm trực tiếp lời tấn công, chưa qua phiên sản phẩm. Cần nối đánh giá qua phiên và rà dữ liệu trước khi kết luận KT-07 hoàn tất. Voice hiện dùng chuỗi bản chép lời, không gọi STT.