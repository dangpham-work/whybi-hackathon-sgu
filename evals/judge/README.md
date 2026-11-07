# Judge – lời giảng có nhãn

`labeled.jsonl`: 60–100 lời giảng (Đăng + Quyền gán nhãn độc lập, ghi `annotator`; mâu thuẫn thì thảo luận rồi ghi nhãn chốt).
Phân bố gợi ý: ~40 % Đạt, ~60 % Chưa đạt; mỗi nút của cây mẫu ≥ 5 lời giảng; có cả lời giảng đúng nhưng ngắn và dài nhưng sai.
Kiểm schema: `cd backend && uv run python ../evals/run.py check` (KT-04). Chấm κ: `run.py judge` (C1-16) → `results/judge.md`.
