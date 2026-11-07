# Dữ liệu mẫu (chủ: Quyền – KT-02)

| Tệp | Nội dung | Nguồn |
|---|---|---|
| `users.json` | 1 GV, 1 QTV, 30 SV (tên giả) | Mục 7.5 đề cương; tên An/Châu/Hà/Dũng/Khang cho ví dụ ghép cặp Hình 6.11 |
| `class.json` | Môn CTDL&GT, lớp "CTDL&GT – Nhóm 02", mã tham gia `CTDL2026` | Figma GV-01/GV-02 |
| `tree_ctdl_gt.json` | Cây 11 nút, 13 cạnh (DAG); rubric đầy đủ cho N5 Con trỏ | Giữ cây C2-02 đã merge, gồm N11 AVL, theo duyệt của điều phối ngày 15/10/2026 |
| `syllabi/` | Ba tài liệu tự soạn: PDF số, DOCX, PDF chỉ có ảnh để thử OCR | Dữ liệu kiểm thử KT-02, không phải giáo trình SGU |

## Nạp bằng một lệnh

```bash
docker compose up -d postgres                      # hoặc cả stack
cd backend && uv run alembic upgrade head          # bảng đã có thì bỏ qua
uv run python ../scripts/seed_db.py                # nạp vào DATABASE_URL (mặc định trong .env / config)
uv run python ../scripts/seed_db.py --check        # chỉ kiểm seed/, không cần CSDL
```

- Chạy lại an toàn: bỏ qua bản ghi đã có (email, mã môn, mã tham gia, cây của lớp).
- Cây đọc đúng schema hợp đồng `backend/app/models/schemas/tree.py` (camelCase); `--check` kiểm DAG, 30 SV, email / MSSV duy nhất, có N5 "Con trỏ".
- Mật khẩu mọi tài khoản: `Whybi@2026` (chỉ dev/demo). Băm Argon2id qua `app.core.security`.
- UUID lớp, phiên bản, nút và cạnh giống API C2-02; lưu đủ mã N/KP/MC/SC và trường rubric C2-09. Cây giữ DRAFT như JSON, cần GV bổ sung/duyệt rubric trước khi phát hành; không tự gán PUBLISHED.
- Nếu lớp đã được nạp bằng seeder cũ với UUID ngẫu nhiên, lệnh báo lỗi và không ghi tiếp; người quản lý dữ liệu cần xử lý bản seed cũ trước khi nạp lại.
- Test không cần Docker: `cd backend && uv run pytest -q tests/integration/test_seed_data.py`.

> Mọi tên, MSSV là dữ liệu minh họa, không phải người thật.
