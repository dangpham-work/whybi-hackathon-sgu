# Checklist giờ 0 (H0 → M0 lúc H1)

> Long chạy theo thứ tự; tích ✅ ngay trong PR đầu tiên. Mốc kiểm tra: kế hoạch §7.2 Bảng 15.

## Trước giờ bắt đầu (T−2 … T−0)

- [ ] Đã hỏi ban tổ chức (kế hoạch §10.3): repo có phải trống không; được mang khung / thẻ / dữ liệu / prompt không; cách tính commit; public hay private.
- [ ] Mỗi máy: `git config user.email` = email GitHub của người đó.
- [ ] Khóa API LLM (chính + dự phòng) và hạn mức đủ cho kiểm thử tải; điền vào `.env` trên VM (không commit).
- [ ] VM: Docker + Compose plugin, mở cổng 80/443, tên miền trỏ đúng IP, chứng chỉ TLS.
- [ ] GitHub secrets cho deploy: `VM_HOST`, `VM_USER`, `VM_SSH_KEY`.

## H0 – H1

- [ ] `cp .env.example .env` → `docker compose up -d --build` → `curl http://localhost/health` trả `{"status":"ok"}`.
- [ ] CI xanh trên `main` (backend ruff + alembic check + pytest; frontend typecheck + test + build; docker build).
- [ ] Bảo vệ nhánh `main`: bắt buộc PR + CI xanh; chỉ Long (Đăng thay) merge.
- [ ] Điền tên GitHub vào `.github/CODEOWNERS`.
- [ ] Tạo nhãn và issue từ thẻ: `bash scripts/setup_labels.sh` · `python scripts/create_issues.py --dry-run` rồi chạy thật.
- [ ] Merge 2 hợp đồng: `app/models/schemas/tree.py` (C2-02), `app/models/schemas/session.py` (C1-01).
- [ ] Nạp cây mẫu CTDL&GT: `seed/tree_ctdl_gt.json` lấy được qua API (M0).
- [ ] Frontend sinh kiểu: `cd frontend && npm run gen:api` không lỗi.
- [ ] Mỗi người mở `docs/status/<tên>.md`, ghi thẻ đang làm.

## M1 (H3)

- [ ] Compose chạy đủ dịch vụ trên VM; URL HTTPS trả `/health` (Quyền xác nhận).
