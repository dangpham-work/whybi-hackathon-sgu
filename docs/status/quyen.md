# docs/status/quyen.md   (chỉ Quyền sửa)

> Cập nhật sau mỗi thẻ (kế hoạch §4.2). Mọi người – và mọi phiên AI – đọc hết `docs/status/` trước khi sửa code.

- Xong:
  - KT-01 – mẫu bug đủ trường (mức, module, bước tái hiện, môi trường); quy trình `docs/bug-triage.md` (PR #74)
  - KT-02 – dữ liệu mẫu `seed/` + `scripts/seed_db.py` nạp bằng một lệnh (PR #77)
  - KT-03 – khung test tích hợp (`backend/tests/integration/conftest.py`, fixture `http` / `api`) và E2E Playwright; job CI `e2e` trên stack docker compose
- Phát sự kiện / hợp đồng đã chốt:
  - Test tích hợp: gắn `@pytest.mark.integration`; mặc định bỏ qua, bật bằng `RUN_INTEGRATION=1` (+ `INTEGRATION_API_URL`, mặc định http://localhost:8000)
  - E2E: `cd e2e && npm ci && npx playwright test` (`E2E_BASE_URL`, mặc định http://localhost); `npm run typecheck` không cần stack
  - CI job `e2e`: song song, lỗi làm CI thất bại (đã bỏ `continue-on-error`); báo cáo ở artifact `playwright-report`
- Đang làm: kiểm chứng lại KT-03 sau PR #92 (đã merge khi CI lỗi vì thiếu nền backend, nginx và frontend; các phần nền đã được bổ sung trên main).
- Cần từ người khác:
  - Long (C2-07): `api/auth.py` dùng `EmailStr` – email-validator chặn đuôi `.test`, `POST /auth/login` với `gv@whybi.test` trả 422 (đã kiểm trên stack local; có test xfail `test_dang_nhap_tai_khoan_demo_khong_bi_422`). Đề xuất: ngoài prod bỏ `"test"` khỏi `email_validator.SPECIAL_USE_DOMAIN_NAMES`, hoặc dùng `str` có pattern
  - Long: duyệt job `e2e` trong `.github/workflows/ci.yml`; thêm `e2e` vào required checks của main để ngăn merge khi test thất bại
  - Người có quyền admin repo: tạo bảng GitHub Projects theo mục 4 `docs/bug-triage.md`
  - GV / thư viện: giáo trình mẫu theo `seed/syllabi/README.md`
