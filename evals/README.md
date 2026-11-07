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

## Định dạng

```jsonc
// guard/attacks.jsonl – một dòng một kịch bản
{"id": "AT01", "type": "JAILBREAK", "channel": "text", "input": "…", "expect": {"flag": "JAILBREAK", "affects_score": false}}
// judge/labeled.jsonl
{"id": "J001", "node": "N5", "transcript": "…", "label": "PASSED|FAILED", "scores": {"CORRECTNESS": 0.8, "COVERAGE": 0.6, "ESSENCE": 0.7, "ROBUSTNESS": 0.5, "CLARITY": 0.9}, "annotator": "Quyền"}
// tutee/sessions.jsonl
{"id": "T01", "node": "N5", "turns": [{"role": "student", "text": "…"}], "leak_annotations": []}
// stt/manifest.jsonl
{"id": "S01", "file": "audio/S01.webm", "reference": "…", "terms": ["con trỏ", "malloc", "free"]}
```
