# docs/status/thang.md   (chỉ Thắng sửa)

> Cập nhật sau mỗi thẻ (kế hoạch §4.2). Mọi người – và mọi phiên AI – đọc hết `docs/status/` trước khi sửa code.

- Xong: GD-01 – khung giao diện 3 vai (GV sidebar + breadcrumb, SV thanh tab dưới, QTV sidebar), ngăn kéo menu dưới 1024px, trang 404; route tự nạp có `handle.screen`
- Phát sự kiện / hợp đồng đã chốt:
  - Menu theo vai ở `frontend/src/lib/nav.ts` (`NAV.LECTURER/STUDENT/ADMIN`) – thêm mục menu thì sửa ở đây.
  - `frontend/src/router.tsx` export `routes` (test / e2e dựng bằng `createMemoryRouter`); màn mới vẫn chỉ cần tạo `src/pages/<vai>/<MÃ>.tsx`.
  - Layout lấy màn đang mở qua `useCurrentScreen()` (`src/layouts/shell.tsx`).
- Đang làm: GD-03
- Cần từ người khác:
  - GD-04 / Long (C2-07): API phiên đăng nhập để thay người dùng mẫu trong layout (hiện lấy tên từ `seed/users.json`).
  - Quyền (e2e): menu có `aria-label="Điều hướng chính"`, breadcrumb `aria-label="Đường dẫn"` – dùng làm bộ chọn.
