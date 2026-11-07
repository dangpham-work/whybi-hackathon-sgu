# Judge – lời giảng có nhãn

`labeled.jsonl`: 60–100 lời giảng (Đăng + Quyền gán nhãn độc lập, ghi `annotator`; mâu thuẫn thì thảo luận rồi ghi nhãn chốt).
Phân bố gợi ý: ~40 % Đạt, ~60 % Chưa đạt; mỗi nút của cây mẫu ≥ 5 lời giảng; có cả lời giảng đúng nhưng ngắn và dài nhưng sai.
Kiểm schema: `cd backend && uv run python ../evals/run.py check` (KT-04). Chấm κ: `run.py judge` (C1-16) → `results/judge.md`.

## Gán nhãn bằng người (`nhan_nguoi.py`)

Nhãn hiện tại vẫn là bản nháp AI, chỉ đổi tên nguồn (xem `evals/NGUON_DU_LIEU.md`). Thay bằng nhãn người như sau:

```bash
cd backend
uv run python ../evals/judge/nhan_nguoi.py xuat --nguoi Quyen      # phiếu mù → evals/judge/phieu/Quyen.csv
uv run python ../evals/judge/nhan_nguoi.py xuat --nguoi Thang
# hai người điền phiếu độc lập (mở bằng Google Sheets / Excel, giữ UTF-8, giữ nguyên cột id)
uv run python ../evals/judge/nhan_nguoi.py nhap ../evals/judge/phieu/Quyen.csv ../evals/judge/phieu/Thang.csv
# thảo luận các mẫu lệch, điền cột "chot" trong phieu/tranh_chap.csv, rồi:
uv run python ../evals/judge/nhan_nguoi.py nhap ../evals/judge/phieu/Quyen.csv ../evals/judge/phieu/Thang.csv \
  --chot ../evals/judge/phieu/tranh_chap.csv --ghi
```

Cách chấm từng cột:
- `nhan`: **Đạt** khi lời giảng nêu đúng mọi ý `(bắt buộc)` trong cột `y_bat_buoc` và không có lỗi sai kiến thức; ngược lại **Chưa đạt**.
- `CORRECTNESS` đúng kiến thức · `COVERAGE` đủ ý bắt buộc · `ESSENCE` nói được bản chất, không chỉ định nghĩa ·
  `ROBUSTNESS` vững trước câu hỏi vặn (lời giảng không kèm hỏi đáp thì chấm theo việc có lường trước hiểu lầm không) ·
  `CLARITY` dễ hiểu, mạch lạc. Thang 0–100.
