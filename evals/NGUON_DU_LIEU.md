# Nguồn gốc và cách xử lý dữ liệu (tiêu chí III.1)

Mọi bộ dữ liệu trong `seed/` và `evals/` đều ghi rõ **ai tạo, tạo bằng cách nào, được dùng vào việc gì**.
Không bộ nào chứa dữ liệu cá nhân thật của sinh viên. Không bộ nào lấy từ giáo trình có bản quyền.
Cột "Trạng thái" phải cập nhật mỗi khi một bộ được người rà xong; **nháp AI không được báo là nhãn người**.

| Bộ dữ liệu | Số mẫu | Tạo bởi | Trạng thái | Dùng cho |
|---|---|---|---|---|
| `seed/users.json` | 1 GV, 1 QTV, 30 SV | Đội soạn, **tên giả** | Dùng được | Demo, test |
| `seed/class.json` | 1 lớp | Đội soạn theo Figma GV-01/GV-02 | Dùng được | Demo |
| `seed/tree_ctdl_gt.json` | 11 nút, 13 cạnh | Đội soạn theo đề cương v0.1 (Hình 2.2, Bảng 6.1) | Rubric N5 theo đề cương; rubric nút khác do Quyền soạn, **chưa GV duyệt** | Demo, rubric cho Judge |
| `seed/syllabi/` | 3 tệp (PDF số, DOCX, PDF ảnh) | Đội tự soạn | Dùng được, **không phải giáo trình SGU** | Kiểm thử đọc tài liệu, OCR |
| `evals/tree/*.gold.json` | 3 cây (CTDL&GT, KTLT, CSDL) | Nháp AI | **Chờ GV xác nhận** | Đo F1 sinh cây (KT-09) |
| `evals/judge/labeled.jsonl` | 62 lời giảng | Lời giảng và nhãn: nháp AI | **Chưa có nhãn người độc lập**, xem mục dưới | Đo κ của Judge |
| `evals/guard/attacks.jsonl` | 58 kịch bản | AT01–AT07 theo Phụ lục B đề cương; AT08–AT58 nháp AI | Chưa có người rà độc lập | Đo tỉ lệ chặn của Guard |
| `evals/tutee/sessions.jsonl` | 30 phiên | Nháp AI | Chưa có người chấm lộ đáp án | Đo tỉ lệ lộ đáp án |
| `evals/stt/manifest.jsonl` + `audio/` | 30 câu | Câu do đội soạn; giọng do thành viên đọc | **Chưa ghi âm** | Đo WER, thuật ngữ |

## Gán nhãn Judge bằng người (thay nháp AI)

Ghi chú: commit `99f5097` đổi `source` của 62 mẫu từ `ai_draft` sang `human` nhưng **không đổi nhãn hay điểm nào**
so với bản nháp AI (`82764f5`). Vì vậy κ = 0,643 trong `results/judge.md` chưa phải κ so với nhãn người.

Quy trình (công cụ `evals/judge/nhan_nguoi.py`):

1. Hai người **không viết prompt Judge** nhận hai phiếu mù `evals/judge/phieu/<tên>.csv`.
   Phiếu chỉ có lời giảng và các ý của rubric, không có nhãn cũ, mỗi người một thứ tự xáo khác.
2. Mỗi người tự điền `nhan` (Đạt / Chưa đạt) và 5 điểm 0–100, **không trao đổi** trong lúc chấm.
3. Chạy `nhap`: đo **κ giữa hai người**. Đây là trần độ khó của bài toán; Judge đạt gần mức này là tốt.
4. Hai người thảo luận các mẫu lệch nhãn, ghi nhãn chốt; `nhap --chot … --ghi` ghi `labeled.jsonl` với `source: "human"`.
5. Chạy Judge bằng model thật (`LLM_MODE=real uv run python ../evals/run.py judge`), ghi cả κ người–người và κ Judge–người.

Phiếu đã điền được commit cùng repo để giám khảo đối chiếu được.

## Ghi âm STT

- Trang `evals/stt/ghi_am.html` (mở qua `python -m http.server`) bắt người nói nhập **mã giả danh** và tick đồng ý
  trước khi ghi. Không lưu tên thật.
- Chỉ những câu đã ghi mới được bật `consent: true` trong manifest. Cần ít nhất 2 người nói.
- Người nói có thể rút đồng ý: xóa tệp trong `audio/`, đặt lại `consent: false`.

## Xử lý dữ liệu của người dùng thật khi vận hành

- Lời giảng của SV luôn được coi là dữ liệu, bọc trong `<student_transcript>` và qua Guard trước khi tới LLM.
- Ghi âm chỉ lưu thêm vào kho tệp khi SV đồng ý (luồng đồng ý ở màn ghi âm).
- Khóa API và `.env` không bao giờ được commit.
