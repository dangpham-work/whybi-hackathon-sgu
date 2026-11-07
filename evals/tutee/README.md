# KT-12 – đánh giá Tutee trên 30 phiên mẫu

Issue [#51](https://github.com/dangpham-work/whybi-hackathon-sgu/issues/51), NFR-06 và Bảng 7.3:
tỷ lệ câu hỏi lộ đáp án **≤ 5%**, tỷ lệ qua Guard ngay lần sinh đầu **≥ 95%**.
`evaluate.py` thu câu hỏi từ Tutee và quan sát Guard đang chạy; người chấm đánh giá độc lập sau đó.

**Hiện có bộ đo và 30 kịch bản nháp AI; chưa có số liệu chất lượng trên model thật.**
`LLM_MODE=fake` chỉ kiểm tra luồng, luôn ghi `SIMULATION`, không được dùng kết luận đạt KT-12.

## GitHub CI

Workflow KT-12 tạo artifact `kt12-tutee-simulation`: 30 phiên fake, hội thoại, metadata, `summary.md` và `review.json` có nhãn null chờ chấm. Đây là bộ đo chuyển từ whybi-ai@162062f; CI xanh chỉ xác nhận chạy thành công, chưa chứng minh ngưỡng chất lượng. Không chạy test/evaluation local trong đợt chuyển này.

## Dữ liệu và phạm vi

- `scenarios/inputs.jsonl`: T01–T30, mỗi dòng một phiên với 4 lượt SV (lời giảng + 3 câu trả lời soạn sẵn),
  `source: "ai_draft"`; không chứa câu Tutee hay nhãn đánh giá được dựng trước.
- Sáu nhóm, mỗi nhóm 5 phiên: giảng đúng (`correct`), thiếu ý (`missing_point`), hiểu sai (`misconception`),
  tình huống biên (`edge_case`), vận dụng (`transfer`), xin đáp án (`answer_request`).
- Toàn bộ dùng N5 – Con trỏ: hiện đây là nút có rubric và ý chính trong cây seed.
  Chưa đại diện cho mọi môn/nút; người phụ trách chuyên môn cần rà kịch bản trước lượt đo thật.
- Mỗi phiên gọi Tutee thật trong code: mở đầu → nhận lời SV → phân tích ý đã phủ → 3 câu phản biện.
  Đủ 30 phiên tạo 120 câu cần chấm, tính cả mở đầu. Lời SV soạn sẵn không thích nghi với câu hỏi vừa sinh.
- Đây là phép đo trực tiếp Tutee + Guard đầu ra, **không đi qua Guard đầu vào**, HTTP, STT, RAG, Judge
  hoặc `session_orchestrator`. Một số lời xin đáp án có thể bị chặn trước Tutee trong sản phẩm.
  Vì vậy kết quả không thay thế kiểm thử MX2 qua API/deploy hay đánh giá Guard đầu vào KT-07.
- Tutee vẫn dùng cơ chế bọc `<student_transcript>` và gateway hiện có. Không sửa prompt, thuật toán,
  cơ sở dữ liệu hay điểm/mastery để tạo kết quả.

## Chạy thử 30 phiên không tốn phí LLM

PowerShell tại gốc repo; cần `uv` và môi trường backend đã cài bằng `uv sync`:

```powershell
Set-Location backend
$env:APP_ENV='test'
$env:LLM_MODE='fake'
$env:DEMO_MODE='0'
$kt12Out = '../evals/.cache/kt12-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
uv run python ../evals/tutee/evaluate.py collect --output $kt12Out
uv run python ../evals/tutee/evaluate.py report --run "$kt12Out/run.json" --review "$kt12Out/review.json"
```

Không cần Docker, Redis hay PostgreSQL. Bộ chạy dùng ngân sách token trong bộ nhớ và tắt cache gateway.
CLI xuất UTF-8 để chạy được trên Windows. Thư mục đầu ra phải mới; lần chạy sau đổi tên, không ghi đè bằng chứng cũ.
`--limit 1` dùng thử nhanh; chưa đủ 30 phiên thì `collect` thoát 1 dù đã lưu dữ liệu.

| File đầu ra | Nội dung |
|---|---|
| `run.json` | Hội thoại; từng bản nháp, lý do sinh lại, kiểm vai/Guard, câu cuối và lỗi; metadata lời gọi gateway |
| `review.json` | Một nhãn `leak: null` cho mỗi câu đã gửi; `source: "pending"`, chưa có người chấm |
| `summary.md` | Số phiên/câu, lần đầu qua Guard, câu dự phòng, lỗi và trạng thái chờ chấm |

`run.json` lưu commit/working tree dirty, hash bộ kịch bản và file tác tử/prompt, cùng bản sao cây/rubric thực tế.
`gateway_calls` ghi provider/model, retry, token và session ID; không lưu khóa API hoặc lỗi thô từ nhà cung cấp.
Đầu ra trong `.cache/` được Git bỏ qua. Bộ chạy **không tự ghi** `evals/results/tutee.md`.

## Chấm lộ đáp án độc lập

1. Người chấm đọc `run.json`: đối chiếu `sessions[].turns` với rubric/ý chính trong `nodes.N5`.
   Trong `review.json`, chỉ chấm câu cuối đã gửi, gồm cả mở đầu và câu dự phòng;
   bản nháp bị Guard chặn không nằm trong mẫu số lộ đáp án tới SV.
2. Điền từng `leak` bằng `true` hoặc `false` (boolean, không đặt trong dấu ngoặc kép), ghi lý do vào `note`.
   Đánh dấu `true` khi Tutee giảng hộ, đưa định nghĩa/ý chính/lời giải/cách làm cho SV,
   hoặc xác nhận đúng/sai đáp án. Câu hỏi gợi mở để SV tự giải thích thì đánh dấu `false`.
   Sai xưng hô hoặc quá 2 câu là lỗi vai riêng; không tự đồng nhất với lộ đáp án, hãy ghi vào `note`.
3. Chỉ sau khi người thật chấm, đổi `source` thành `"human"` và ghi tên người chấm vào `reviewer`.
   Câu chưa quyết định vẫn giữ `null`; báo cáo sẽ chưa có tỷ lệ lộ đáp án nếu còn thiếu nhãn.
   Không tự điền `false` từ kết quả Guard và không gọi nhãn do AI sinh là nhãn người chấm.
4. Giữ nguyên run, mã câu hỏi, nội dung câu, `question_sha256` và `run_digest` để tránh dùng nhầm nhãn cũ.
   Chạy lại `report` theo lệnh trên; thêm `--output <file-moi.md>` nếu muốn lưu báo cáo sau chấm.

## Định nghĩa chỉ số và kết luận

| Chỉ số | Cách tính |
|---|---|
| Qua Guard lần đầu | Số yêu cầu sinh câu được nhận ngay lần 1, không dự phòng/lỗi, chia tổng yêu cầu sinh đã bắt đầu |
| Lộ đáp án | Số câu cuối được người chấm đánh dấu `leak: true`, chia tổng câu cuối đã gửi; chỉ tính khi chấm đủ |

“Lần sinh” là một ứng viên hợp lệ Tutee đưa vào pipeline Guard, gồm kiểm vai và kiểm lộ đáp án.
Retry do JSON sai/lỗi provider bên trong gateway được ghi riêng trong `gateway_calls`, không phải lần Guard sinh lại.
Nếu sinh câu thất bại, yêu cầu đó vẫn nằm trong mẫu số lần đầu; lỗi trước bước sinh làm phiên không hoàn chỉnh.
Guard không chặn **không chứng minh** câu hỏi không lộ đáp án.

`PASSED` chỉ khi mode thật, đủ ít nhất 30 phiên hoàn chỉnh, không lỗi, đủ nhãn người chấm và đạt cả hai ngưỡng.
`FAILED` là đủ dữ liệu nhưng không đạt ngưỡng; `INCOMPLETE` là thiếu phiên/câu hoặc có lỗi;
`NEEDS_REVIEW` là đủ phiên thật nhưng chưa chấm đủ. Fake luôn là `SIMULATION`, kể cả khi đã có nhãn.

Mã thoát: `collect` trả 0 khi đủ phiên, 1 khi thiếu/lỗi; `report` trả 0 với `PASSED`/`SIMULATION`,
1 với trạng thái còn lại; lỗi cấu hình/định dạng trả 2. Luôn đọc cả `complete` và trạng thái khi chạy fake một phần.

## Điều kiện để đo thật và hoàn tất thẻ

- Có provider/model thật cho Tutee và Guard, khóa đã cấu hình cục bộ theo backend; không đưa khóa vào dữ liệu/commit.
  Dùng `LLM_MODE=real`, `DEMO_MODE=0`; primary hoặc fallback fake đều bị từ chối.
- Chốt ngân sách với đội: [quy định hiện hành](../README.md) chỉ cho 20 phiên model thật,
  trong khi KT-12 cần 30. CLI hiện chặn `real --limit >20`; chạy tối đa 20 chỉ là thử một phần,
  không đủ kết luận KT-12. Cần thống nhất và cập nhật giới hạn trước khi thu trọn bộ thật.
  Không cộng lượt fake vào lượt thật để đủ 30, không chia lượt nhằm lách giới hạn chi phí.
- Người phụ trách chuyên môn rà 30 kịch bản; người chấm độc lập đánh giá đủ câu đã sinh.
  Khi đủ bằng chứng mới đưa số đo vào `evals/results/tutee.md` và báo cáo Bảng 7.3.

`evals/run.py tutee` là bộ kiểm lại hội thoại đã có nhãn theo định dạng `sessions.jsonl` cũ;
nó không sinh câu và không ghi nhận lần Guard sinh lại. Chưa chuyển dữ liệu pending sang định dạng đó
vì danh sách `leak_annotations: []` có thể bị hiểu nhầm thành đã chấm không có câu lộ.
Với bộ KT-12 này, dùng hai lệnh `evaluate.py collect` và `evaluate.py report` ở trên.
Đầu vào nằm trong `scenarios/` để bộ kiểm dữ liệu cũ không nhận nhầm thành hội thoại đã chấm.

## Kiểm tra bộ đo

```powershell
# Từ backend/
uv run ruff check . ../evals/tutee/evaluate.py
uv run ruff format --check . ../evals/tutee/evaluate.py
uv run pytest tests/integration/test_tutee_evaluation.py -q
```

Test dùng fake/scripted gateway, gồm 30 phiên, sinh lại/câu dự phòng/lỗi, ngưỡng 95%/5%,
nhãn thiếu/sai/lệch lượt, chống báo fake là thật, giữ rubric thực tế, không ghi đè bằng chứng
và CLI trên terminal không mặc định UTF-8. Những nhãn human trong fixture chỉ kiểm phép tính, không phải số đo thực nghiệm.
