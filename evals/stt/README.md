# KT-10 – giọng nói và đánh giá STT

Thẻ [#49](https://github.com/dangpham-work/whybi-hackathon-sgu/issues/49): 30 đoạn ghi âm, WER, tỉ lệ thuật ngữ đúng,
p95 độ trễ STT; luồng ghi âm → xác nhận → gửi. Mục tiêu WER ≤ 15%; NFR-02: p95 ≤ 4 giây cho âm thanh 60 giây.

**Dữ liệu hiện tại chưa đủ để đo chất lượng:** manifest có 30 bản lời tham khảo, chưa có tệp âm thanh;
tất cả `consent=false`. Không tự tạo giọng AI rồi tính là 30 mẫu giọng người, không tự bật consent.

## Phạm vi công cụ và test

| Thành phần | Kiểm được | Giới hạn |
|---|---|---|
| `metrics.py` | WER, thuật ngữ theo căn chỉnh, p95 nearest rank | Không chứng nhận bản chép chuẩn |
| `evaluate.py` | Adapter STT → SpeechService → bản chép trước chỉnh sửa; WER thô và sau chuẩn hóa | Không đo HTTP/UI hoặc ghi MinIO; trạng thái đạt phần đo vẫn là PARTIAL_SCOPE |
| `test_stt_evaluation.py` | Công thức, báo cáo, dữ liệu thiếu/trùng, fake/real, retry, WebM không có duration header | Fixtures tổng hợp, không phải kết quả nhận dạng người thật |
| `test_voice_flow.py` | API upload → bản chép confidence 0,65 → gửi bản sửa VOICE → đọc lại phiên; lỗi và consent | PostgreSQL thật; STT/LLM, auth và kho tệp giả lập |
| `e2e/tests/voice-flow.spec.ts` | Đồng ý/từ chối, MediaRecorder, dạng sóng, dừng/ghi lại/gửi, tự dừng 3 phút, lỗi STT | Chromium dùng micro giả, API có kịch bản; kiểm đồng hồ bằng Playwright clock |

GD-08 #64 / PR #143 chưa merge vào main: ca TC07 xác nhận/sửa qua SV-05 giữ `test.fixme`, không tính là đạt.
Test API gửi trường `transcriptEdited=true` và kiểm nội dung đã sửa qua GET phiên; chưa chứng minh thao tác SV-05.
Spec `voice-flow.spec.ts` chạy trên project `gv-desktop` (tên project có sẵn), không tự chạy trên Pixel 7 vì bộ lọc tên file.

## Chuẩn bị 30 ghi âm

Mỗi dòng `manifest.jsonl` có `id`, `file`, `reference`, `terms`, `speaker`, `consent`:

- `id`: S01…S30; `file`: `audio/S01.webm` hoặc WAV/MP3/M4A/OGG. Tệp đặt trong `evals/stt/audio/`.
- Mỗi đoạn 30–120 giây; dùng ít nhất hai người nói, `speaker` là mã giả danh, không cần tên thật.
- Người nói đồng ý sử dụng giọng cho đánh giá rồi mới điền `consent=true`. Đây khác với đồng ý lưu thêm bản ghi vào MinIO.
- Nghe và sửa `reference` đúng nội dung thực nói. Lời tham khảo ngắn hiện tại chưa phải transcript của đoạn 30–120 giây.
- `terms` là các thuật ngữ xuất hiện nguyên cụm trong reference. Không thêm thuật ngữ chỉ để nâng điểm.
- Các tệp phải khác nhau về nội dung. Bộ đo kiểm hash; người duyệt vẫn cần kiểm độc lập/ngữ cảnh, không phải chỉ đổi container âm thanh.

Để xét ngưỡng p95 cho 60 giây, **quy ước của bộ đo này** yêu cầu ít nhất 20 mẫu dài 60±0,5 giây trong bộ dữ liệu.
Đây là quy ước lấy mẫu, không phải ngưỡng cỡ mẫu ghi trong NFR-02. Vẫn báo p95 cho nhóm ít mẫu nhưng để kết luận ngưỡng là `null`.
Không lấy p95 của nhóm 30 giây hoặc trộn 30–120 giây để kết luận đạt yêu cầu 60 giây.

Chuẩn bị riêng JSON ngữ cảnh nút thật, dạng `{ "S01": <Node>, "S02": <Node>, ... }`, dùng schema Node của backend:

```json
{
  "S01": { "key": "con_tro", "title": "Con trỏ", "description": "Nội dung nút đã chốt trong lớp" }
}
```

Ví dụ chỉ minh họa định dạng; khi đo phải lấy đủ ngữ cảnh Node/rubric thực tế. Không dựng hints từ `reference`/`terms` của đáp án.
Thiếu context vẫn có thể đo thô nhưng báo cáo không công nhận đủ bộ. Node được lưu trong bằng chứng để người duyệt đối chiếu.

## Chạy bộ đo

PowerShell từ gốc repo:

```powershell
Set-Location backend
uv sync --frozen
$env:APP_ENV='test'
$env:LLM_MODE='fake'
$env:DEMO_MODE='0'
uv run python ../evals/stt/evaluate.py collect --output ../evals/.cache/kt10-check
```

Đầu ra phải là thư mục mới. Với manifest hiện tại: `0/30`, mỗi dòng có `MISSING_AUDIO, CONSENT_REQUIRED`,
exit **1**, WER/p95 để trống. Đây là báo cáo thiếu dữ liệu đúng dự kiến; không có lời gọi STT cho các dòng này.
Khi có file và consent, fake chạy được luồng nhưng luôn mang nhãn SIMULATION, không kết luận chất lượng thật.

Khi đủ ghi âm và có dịch vụ STT thực tế, cấu hình `STT_PROVIDER=whisper|cloud` theo `backend/app/core/config.py`:
Whisper dùng `STT_WHISPER_URL`; cloud dùng `OPENAI_COMPAT_BASE_URL` và khóa riêng trong môi trường.
Đặt `LLM_MODE=real` (cờ này cũng điều khiển adapter STT), giữ `DEMO_MODE=0`, rồi chạy:

```powershell
uv run python ../evals/stt/evaluate.py collect --contexts ../evals/.cache/kt10-contexts.json --output ../evals/.cache/kt10-real
```

`--root <thư-mục>` thay gốc dữ liệu, bên trong cần `stt/manifest.jsonl` và `stt/audio/`.
WAV đọc thời lượng bằng thư viện chuẩn; định dạng nén cần `ffprobe` trên PATH (image backend đã có FFmpeg).
WebM do MediaRecorder tạo có thể thiếu duration header; bộ đo dùng mốc thời gian các packet audio khi cần.
Thiếu probe/thời lượng lỗi → `DURATION_UNAVAILABLE`, không gọi provider để tính một mẫu có thời lượng không rõ.

Đo tuần tự, không warm-up riêng; ghi thời gian gọi adapter (cộng cả retry) và SpeechService. Bóc metadata thời lượng
ở ngoài khoảng đo. Service chạy `consent=False` để không tạo thêm bản âm thanh trong MinIO; không cần DB/kho đối tượng.
Vì vậy số đo chưa bao gồm mạng client/API, ghi MinIO hoặc thao tác xác nhận trên UI. Ghi cấu hình máy/dịch vụ STT và điều kiện
chạy trong ghi chú người duyệt trước khi so sánh nhiều lượt.

## Bằng chứng và duyệt

Mỗi lượt tạo `run.json`, `review.json`, `summary.md`; không ghi đè và không tự sửa `evals/results/stt.md`.
Run chứa transcript thô/sau chuẩn hóa, consent/speaker/context, hash audio, thời lượng, số lần gọi, provider/model,
ngưỡng confidence, commit/dirty và hash mã nguồn. Không chép âm thanh vào báo cáo; lỗi provider được thay bằng mã cố định.

Người duyệt nghe đối chiếu tất cả reference/context/consent và thời lượng. Trong `review.json`, điền
`source="human"`, `reviewer`, `approved=true|false`, `note`; giữ nguyên `run_id`, `run_digest`.
Phiếu này ghi nhận thẩm định, không phải chữ ký số. Đổi dữ liệu/run thì phải thu và duyệt lại.

```powershell
uv run python ../evals/stt/evaluate.py report --run ../evals/.cache/kt10-real/run.json --review ../evals/.cache/kt10-real/review.json --output ../evals/.cache/kt10-reviewed.md
```

| Trạng thái | Ý nghĩa |
|---|---|
| SIMULATION | Provider fake; không công nhận chất lượng/độ trễ thật |
| INCOMPLETE | Chưa đủ ≥30 mẫu thành công khác nhau, 30–120 s, consent, speaker, context hoặc bằng chứng gọi provider |
| NEEDS_REVIEW | Đủ dữ liệu nhưng chưa được người duyệt xác nhận |
| FAILED | Đã duyệt nhưng WER > 15%, hoặc nhóm đủ mẫu 60 s có p95 > 4 s |
| PARTIAL_SCOPE | Phần đo đã duyệt không vượt ngưỡng được xét; xem riêng `latency_target_met` vì có thể chưa đủ mẫu 60 s; chưa nghiệm thu toàn KT-10 |

`collect`: exit 0 khi mọi mẫu xử lý được, 1 nếu thiếu/lỗi; **0 không có nghĩa là đạt chất lượng**.
`report`: exit 0 chỉ cho fake xử lý đủ mẫu, còn lại 1 vì phạm vi chưa đầy đủ. Cấu hình/phiếu sai hoặc ghi đè bị từ chối trả 2.
Mẫu lỗi vẫn trong tổng số và ngăn công nhận đủ bộ; p95 được báo chỉ trên mẫu thành công, không che tỷ lệ lỗi.

## Quy tắc chỉ số

- Chuẩn hóa NFKC, chữ thường, thay dấu câu bằng khoảng trắng; giữ dấu tiếng Việt và ký hiệu như `C++`.
  Token theo khoảng trắng (tiếng Việt tính theo đơn vị tách bởi khoảng trắng, không dùng bộ tách từ ngôn ngữ).
- WER = `(thay + xóa + chèn) / số token reference`; có thể vượt 100%. Reference rỗng bị từ chối.
  WER corpus cộng số lỗi và số token, không lấy trung bình WER các câu. Báo cả trước và sau chuẩn hóa thuật ngữ, trước chỉnh sửa của SV.
- Thuật ngữ đúng = số lần xuất hiện khớp nguyên cụm trên căn chỉnh WER / số lần trong reference.
  Tên lặp được đếm từng lần; `freezer` không tính là `free`; chèn từ giữa `con trỏ` không tính nguyên cụm.
  Không có ngưỡng đạt riêng cho thuật ngữ trong Bảng 7.3 nên chỉ báo số đo. Khi căn chỉnh hòa điểm, ưu tiên chéo → xóa → chèn.
- p95 dùng nearest rank: phần tử thứ `ceil(0,95 × n)` sau sắp xếp; không có mẫu trả `null`, không trả 0 giây.

## Chạy test

Từ `backend/`:

```powershell
uv run pytest tests/integration/test_stt_evaluation.py -q
# Test API cần TEST_DATABASE_URL tới PostgreSQL/pgvector test riêng đã migrate:
uv run pytest tests/integration/test_voice_flow.py -q
```

Ca FFmpeg thật bị skip nếu máy chưa có ffmpeg/ffprobe; image `backend/Dockerfile` có đủ.
DB thiếu thì test API skip. Trên Windows nếu lỗi quyền temp, thêm `-p no:cacheprovider --basetemp .cache/<tên-lượt-mới>`.

Frontend cần chạy từ đúng nhánh (ví dụ `npm.cmd run dev -- --host 127.0.0.1 --port 4178` trong `frontend/`).
Ở terminal khác, từ `e2e/`:

```powershell
$env:E2E_BASE_URL='http://127.0.0.1:4178'
npm.cmd run typecheck
npx.cmd playwright test tests/voice-flow.spec.ts --project=gv-desktop --workers=1
```

Test trình duyệt tự dùng microphone giả và API có kịch bản; không gọi micro người dùng và không ghi dữ liệu vào lớp thật.
Xem kết quả thực chạy trong [trạng thái Quyền](../../docs/status/quyen.md).
