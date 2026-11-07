# Bộ đánh giá AI (Bảng 7.3 đề cương) – Quyền

| Thư mục | Thành phần | Dữ liệu | Chỉ số | Chỉ tiêu | Thẻ |
|---|---|---|---|---|---|
| `tree/` | Sinh cây kỹ năng | 3–5 đề cương + cây chuẩn (`<môn>.gold.json`) | P / R / F1 nút, cạnh | F1 cạnh ≥ 0,70 | KT-09 |
| `judge/` | Judge | 60–100 lời giảng có nhãn (`labeled.jsonl`) | Cohen’s κ, ma trận nhầm lẫn | κ ≥ 0,60 | KT-04, C1-16 |
| `guard/` | Guard | ≥ 50 kịch bản tấn công (`attacks.jsonl`) | Tỉ lệ chặn; tỉ lệ Đạt sai | ≥ 90 %; 0 % | KT-07 |
| `tutee/` | Tutee | 30 phiên mẫu (`sessions.jsonl`) | Tỉ lệ câu hỏi lộ đáp án | ≤ 5 % | KT-12 |
| `stt/` | STT | 30 đoạn ghi âm có thuật ngữ (`audio/` + `manifest.jsonl`) | WER, tỉ lệ thuật ngữ đúng | WER ≤ 15 % | KT-10 |
| `perf/` | Hiệu năng | 20 / 50 / 100 phiên đồng thời (k6) | p50 / p95 độ trễ, lỗi | p95 ≤ 5 s | KT-13 |

- Kết quả ghi vào `results/<thành phần>.md` theo mẫu sẵn, rồi điền vào Bảng 7.3 của đề cương (KT-17).
- **Không điền số liệu giả định.** Chạy đo hạ tầng với `LLM_MODE=fake`; chỉ 20 phiên dùng model thật (rủi ro chi phí – kế hoạch Bảng 20).
- Ghi âm trong `stt/audio/` được commit (ngoại lệ trong `.gitignore`) – chỉ dùng giọng người đã đồng ý.

## Kiểm dữ liệu (KT-04)

```bash
cd backend && uv run python ../evals/run.py check   # đọc mọi bộ theo schema evals/eval_datasets.py, thoát 1 nếu hỏng
```

- Schema Pydantic trong `eval_datasets.py` (trường lạ là lỗi, kể cả trong cây chuẩn): dòng sai báo đúng `<file>:<dòng>`; id trùng, cờ / tiêu chí / nhãn
  ngoài hợp đồng (`app/models/enums.py`), cây chuẩn có chu trình đều là lỗi. Test: `backend/tests/integration/test_eval_datasets.py`.
- Thiếu so với chỉ tiêu (số mẫu, file ghi âm, giáo trình kèm cây chuẩn) chỉ là **cảnh báo**.
- `judge/labeled.jsonl` hiện là **nháp do AI soạn** (`source: "ai_draft"`, `annotator: "Quyền (nháp AI)"`): dùng để chạy thử
  luồng, **không** dùng để báo κ. Người gán nhãn độc lập xong thì đổi `source` thành `"human"` và ghi tên thật.
- `stt/manifest.jsonl` có 30 kịch bản đọc; file `audio/Sxx.webm` chưa ghi. Ghi xong và người nói đồng ý → `consent: true`.
- `tree/*.gold.json`: `ctdl_gt` lấy từ cây mẫu seed; `ktlt`, `csdl` là nháp chờ GV xác nhận và chưa có giáo trình kèm.

## Định dạng

```jsonc
// guard/attacks.jsonl – một dòng một kịch bản; expect phải có ≥ 1 kỳ vọng, flag ∈ FlagType
{"id": "AT01", "type": "JAILBREAK", "channel": "text", "input": "…", "expect": {"flag": "JAILBREAK", "affects_score": false}}
// judge/labeled.jsonl – scores đủ 5 tiêu chí, thang 0–100 như CriterionScore (C1-01); node ∈ cây mẫu seed/
{"id": "J001", "node": "N5", "transcript": "…", "label": "PASSED|FAILED", "scores": {"CORRECTNESS": 80, "COVERAGE": 60, "ESSENCE": 70, "ROBUSTNESS": 50, "CLARITY": 90}, "annotator": "Quyền", "source": "human|ai_draft", "covered_points": ["KP1"], "missing_points": ["KP3"]}
// tutee/sessions.jsonl – leak_annotations: chỉ số lượt tutee bị đánh dấu lộ đáp án (KT-12)
{"id": "T01", "node": "N5", "turns": [{"role": "student", "text": "…"}, {"role": "tutee", "text": "…"}], "leak_annotations": []}
// stt/manifest.jsonl – mỗi thuật ngữ phải xuất hiện trong reference
{"id": "S01", "file": "audio/S01.webm", "reference": "…", "terms": ["con trỏ", "malloc", "free"], "consent": false}
// tree/<mã>.gold.json – định dạng TreeVersion (camelCase) + subject, syllabus, aliases {key nút: [tên đồng nghĩa]}
{"subject": "…", "syllabus": "seed/syllabi/….pdf", "aliases": {"n5_con_tro": ["Pointer"]}, "nodes": [{"key": "n5_con_tro", "title": "Con trỏ"}], "edges": []}
```
