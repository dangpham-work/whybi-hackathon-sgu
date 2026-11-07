# Judge – lời giảng có nhãn

`labeled.jsonl`: 60–100 lời giảng (Đăng + Quyền gán nhãn độc lập, ghi `annotator`; mâu thuẫn thì thảo luận rồi ghi nhãn chốt).
Phân bố gợi ý: ~40 % Đạt, ~60 % Chưa đạt; mỗi nút của cây mẫu ≥ 5 lời giảng; có cả lời giảng đúng nhưng ngắn và dài nhưng sai.
Chạy: `cd backend && uv run python ../evals/run.py judge` (KT-04) → `results/judge.md` (κ, ma trận nhầm lẫn).
