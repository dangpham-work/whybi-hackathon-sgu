# KT-09 – kiểm thử MX1 và đo cây kỹ năng

Thẻ [#48](https://github.com/dangpham-work/whybi-hackathon-sgu/issues/48), FR-SK-01…09, MT1:
F1 cạnh ≥ 0,70 trên 3–5 đề cương có cây chuẩn; sinh cây ≤ 180 giây cho đề cương khoảng 30 trang.
Bộ này chuẩn bị test backend và công cụ đo. **Chưa đủ bằng chứng nghiệm thu KT-09.**

## Phạm vi

| Thành phần | Kiểm được | Giới hạn |
|---|---|---|
| `backend/tests/integration/test_mx1_pipeline.py` | Upload PDF/DOCX/bản quét → worker → DAG/rubric → duyệt → phát hành → trạng thái SV; lỗi tệp và phục hồi rubric | PostgreSQL thật; auth, kho tệp, broker, kênh tiến độ và provider giả lập |
| Ca Tesseract trong cùng file | OCR `vie+eng` trên bản quét mẫu rồi chạy tiếp đến rubric | Cần Tesseract; không đánh giá độ chính xác OCR trên tập thực tế |
| `metrics.py`, `test_tree_evaluation.py` | P/R/F1, ánh xạ nút, tính toàn vẹn báo cáo, CLI | Test dùng fake; không chứng minh chất lượng model |
| `evaluate.py collect` | Bóc chữ/OCR → `TreeBuilder` → hậu xử lý DAG; đo riêng từng công đoạn | Không gọi HTTP/queue, không đo RAG/rubric hay upload → `tree.generated` |

TC01, TC03–TC05 được kiểm ở API/backend. Phần tô chu trình, kéo thả, tiến độ và duyệt qua UI
chờ GD-05/GD-09. TC02 với đề cương ~30 trang, ≥ 15 nút và thời gian toàn pipeline còn phải chạy thực tế.
Hai nút có kịch bản trong test không thay cho TC02.

## Dữ liệu cần chuẩn bị

Mỗi môn có `tree/<mã>.gold.json`: schema `TreeVersion` như `seed/tree_ctdl_gt.json`, thêm
`subject`, `syllabus` (đường dẫn PDF/DOCX từ gốc repo, hoặc tuyệt đối), `aliases` và `_source`.
`aliases` ánh xạ **key nút chuẩn** sang danh sách tên đồng nghĩa. Cây chuẩn phải là DAG, không có cạnh trùng,
không có tên/alias trỏ tới nhiều nút. Người duyệt phải kiểm cây và alias đúng với chính tài liệu được đo.

Hiện có 3 cây chuẩn **nháp AI, chưa được GV xác nhận**:

- `csdl`, `ktlt`: chưa gắn giáo trình; được giữ thành dòng lỗi `MISSING_SYLLABUS` trong báo cáo.
- `ctdl_gt`: gắn PDF tổng hợp 1 trang; cây chuẩn 11 nút/13 cạnh bao phủ rộng hơn tài liệu.
  Cặp này chỉ dùng kiểm công cụ, cần hiệu chỉnh và duyệt trước khi đánh giá chất lượng.
- Ba tệp PDF số/DOCX/bản quét trong `seed/syllabi/` là fixture kiểm định dạng, không phải 3 cặp benchmark đã duyệt.

Cần 3–5 giáo trình khác nhau (hash nội dung khác nhau), mỗi cây chuẩn có cạnh để đo F1 cạnh.
Không sao chép cùng tệp dưới nhiều tên để đủ số mẫu. Chuẩn bị dữ liệu và chốt quy ước cạnh trước khi chạy model.

## Chạy thử bằng fake

PowerShell, từ gốc repo; cần `uv`, không cần PostgreSQL cho bộ đo này:

```powershell
Set-Location backend
uv sync --frozen
$env:APP_ENV='test'
$env:LLM_MODE='fake'
$env:DEMO_MODE='0'
uv run python ../evals/tree/evaluate.py collect --case ctdl_gt --output ../evals/.cache/kt09-smoke
```

`--output` phải là thư mục mới; đổi tên khi chạy lại. Bỏ `--case` để thu toàn bộ cây chuẩn:

```powershell
uv run python ../evals/tree/evaluate.py collect --output ../evals/.cache/kt09-all
```

Với dữ liệu hiện có, lệnh thứ hai trả exit code **1**, vì `csdl` và `ktlt` thiếu giáo trình.
Lệnh một cặp trả **0** khi thu xong, nhưng trạng thái vẫn là **SIMULATION**.
Fake trả khái niệm mẫu nên F1 cạnh hiện là 0; số này không đánh giá năng lực model thật.
`--root <thư-mục>` đọc `<thư-mục>/tree/*.gold.json`; `--case <mã>` có thể lặp để chọn tập con.

Mỗi lượt sinh ba file UTF-8, không ghi đè `evals/results/tree.md`:

- `run.json`: cây dự đoán, bản chụp gold, hash giáo trình/gold/mã nguồn, commit và trạng thái dirty,
  thời gian, số trang, trang OCR, cạnh bị DAG loại, lỗi từng mẫu, metadata lời gọi JSON qua gateway.
- `review.json`: phiếu chờ người duyệt, gắn với hash toàn bộ run và từng cặp dữ liệu.
- `summary.md`: P/R/F1 từng mẫu và tổng hợp; mẫu thiếu/lỗi vẫn xuất hiện.

Gateway log chưa ghi từng lời gọi embedding. Bộ đo lưu cấu hình provider/model chính và dự phòng,
không lưu prompt, khóa hoặc lỗi thô từ provider. Chạy CLI trong tiến trình riêng; không nhúng bộ thu log này vào API server.

## Đo thật và duyệt kết quả

Khi có dữ liệu chuẩn và cấu hình model, đặt `LLM_MODE=real`, `DEMO_MODE=0`, cấu hình
provider/model/khóa theo `backend/app/core/config.py` rồi chạy `collect` như trên với thư mục mới.
Mọi lời gọi JSON/embedding vẫn đi qua `LLMGateway`; cache tắt. Cấm primary/fallback fake trong lượt real.

GV đọc tài liệu, gold và bảng đối chiếu. Trong `review.json`, chỉ người duyệt thực tế điền
`source: "human"`, `reviewer`, `approved: true|false` và `note` cho từng cặp; giữ nguyên id/hash.
Phiếu này ghi nhận thẩm định chuyên môn, không phải chữ ký số chống sửa đổi. Đổi dữ liệu/run thì phải thu và duyệt lại.

```powershell
uv run python ../evals/tree/evaluate.py report --run ../evals/.cache/kt09-all/run.json --review ../evals/.cache/kt09-all/review.json --output ../evals/.cache/kt09-reviewed.md
```

Report tính lại từ cây, không tin trường `scores` đã lưu. Trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| `SIMULATION` | Fake, chỉ kiểm công cụ |
| `INCOMPLETE` | Chưa đủ 3–5 giáo trình khác nhau, có lỗi/thiếu thời gian/cạnh chuẩn, hoặc thiếu trace JSON thành công cho từng cặp với provider/model đã cấu hình |
| `NEEDS_REVIEW` | Đủ bằng chứng nhưng chưa được người duyệt xác nhận toàn bộ |
| `FAILED` | Đã duyệt, nhưng micro hoặc macro F1 cạnh < 0,70 |
| `PARTIAL_SCOPE` | Đã duyệt và đạt cả micro/macro F1 cạnh; chưa có thời gian toàn pipeline, chưa nghiệm thu MT1 |

`collect` trả 0 nếu mọi mẫu đã chọn xử lý được, 1 nếu có mẫu lỗi. `report` chỉ trả 0 cho
SIMULATION xử lý đủ mẫu; các trạng thái real vẫn trả 1 vì chưa nghiệm thu toàn phạm vi. Cấu hình/phiếu sai hoặc
đầu ra đã tồn tại trả 2. Luôn đọc trạng thái, không dùng exit code collect để kết luận chất lượng.

## Quy tắc tính điểm

Chuẩn hóa tên bằng Unicode NFKC, casefold, gộp khoảng trắng; giữ dấu tiếng Việt và toán tử.
Khớp tên hoặc alias, không khớp theo key/LLM. Mỗi nút chuẩn nhận tối đa một nút dự đoán:
ưu tiên tên chuẩn, rồi key dự đoán theo thứ tự từ điển; không dùng cạnh để chọn ánh xạ có điểm cao hơn.
Nút dư tính FP. Cạnh có hướng, đảo chiều hoặc nối nút chưa khớp vẫn là FP. Scorer không tự rút gọn cạnh bắc cầu;
`collect` đo cây sau hậu xử lý DAG của sản phẩm và lưu những cạnh đã bị loại.

`P = TP/(TP+FP)`, `R = TP/(TP+FN)`, `F1 = 2TP/(2TP+FP+FN)`.
Mẫu số 0 trả `null`/dấu “—”, không coi tập rỗng là điểm hoàn hảo. Micro cộng TP/FP/FN;
macro lấy trung bình các giá trị xác định theo tài liệu, kèm số mẫu `defined` trong JSON.
Chọn kiểm **cả micro và macro F1 cạnh ≥ 0,70** để tài liệu lớn không che khuất các tài liệu nhỏ.

## Chạy test

Từ `backend/`, không cần DB để kiểm metrics/runner:

```powershell
uv run pytest tests/integration/test_tree_evaluation.py -q
```

Test pipeline cần PostgreSQL có pgvector, đã `alembic upgrade head`, và DB riêng cho test.
Ví dụ tạo container riêng (chỉ chạy lệnh tạo lần đầu):

```powershell
docker run -d --name whybi-kt09-postgres -e POSTGRES_USER=whybi -e POSTGRES_PASSWORD=whybi -e POSTGRES_DB=whybi_kt09 -p 127.0.0.1:55439:5432 pgvector/pgvector:pg16
$env:DATABASE_URL='postgresql+psycopg://whybi:whybi@127.0.0.1:55439/whybi_kt09'
$env:TEST_DATABASE_URL=$env:DATABASE_URL
$env:APP_ENV='test'
$env:LLM_MODE='fake'
$env:DEMO_MODE='0'
# Đợi pg_isready báo accepting connections trước khi migrate.
docker exec whybi-kt09-postgres pg_isready -U whybi -d whybi_kt09
uv run alembic upgrade head
uv run pytest tests/integration/test_tree_evaluation.py tests/integration/test_mx1_pipeline.py -q
```

Test dùng transaction rollback. Thiếu DB thì pipeline bị skip; thiếu Tesseract hoặc `vie+eng` thì ca OCR thật bị skip.
Image từ `backend/Dockerfile` đã có Tesseract tiếng Việt; có thể chạy pytest trong image với dependency dev
(`uv sync --frozen`), mount repo và đặt `TEST_DATABASE_URL` tới DB riêng để kiểm ca này.
Nếu Windows lỗi quyền thư mục tạm pytest, thêm `-p no:cacheprovider --basetemp .cache/<tên-lượt-mới>`.
Sau khi xong, dừng đúng container test bằng `docker stop whybi-kt09-postgres`.

Kết quả thực chạy và phần còn chờ được ghi trong [trạng thái Quyền](../../docs/status/quyen.md).
