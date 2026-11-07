# Tài khoản và Quản trị

> Bản tóm lược để làm việc. Nội dung gốc: [đề cương](README.md). Đổi hợp đồng ⇒ báo trong `docs/status/`.

## Yêu cầu chức năng

| Mã | Yêu cầu | Tác nhân | Ưu tiên |
|---|---|---|---|
| FR-AD-01 | Đăng nhập / đăng xuất, quên mật khẩu, cập nhật hồ sơ | Mọi người dùng | M |
| FR-AD-02 | Phân quyền theo vai trò (GV, SV, QTV) | Hệ thống | M |
| FR-AD-03 | Quản lý tài khoản; nhập danh sách SV từ CSV | QTV | S |
| FR-AD-04 | Quản lý danh mục môn học | QTV | S |
| FR-AD-05 | Cấu hình nhà cung cấp LLM, STT, TTS; mô hình dự phòng | QTV | M |
| FR-AD-06 | Đặt hạn mức token / phút ghi âm theo lớp, theo SV | QTV | S |
| FR-AD-07 | Xem nhật ký, xử lý cờ vi phạm | QTV | S |
| FR-AD-08 | Thông báo trong ứng dụng và email | Hệ thống | S |

## Đọc thêm trong đề cương

- 3.3.5 – [03-yeu-cau](outline/03-yeu-cau.md)
- 5.6 Bảo mật và quyền riêng tư – [05-thiet-ke](outline/05-thiet-ke.md)

## Vị trí mã

- `backend/app/api/auth.py`
- `backend/app/api/admin.py`
- `backend/app/core/security.py`
- `backend/app/models/users.py`
- `frontend/src/pages/auth/AUTH01.tsx`
- `frontend/src/pages/admin/`

## Thẻ việc liên quan

| Thẻ | Người | Vòng | Nội dung |
|---|---|---|---|
| C1-02 | Đăng | 1 (M) | LLM Adapter: nhà cung cấp Gemini và loại tương thích OpenAI, model dự phòng, ép JSON theo schema, thử lại khi lỗi parse, cache, LLM_MODE=fak… |
| C2-07 | Long | 1 (M) | Xác thực và phân quyền: đăng nhập, đăng xuất, quên mật khẩu, cập nhật hồ sơ, GET /me; JWT 30 phút; Argon2 hoặc bcrypt; vai GV, SV, QTV; kiểm… |
| C2-18 | Long | 2 (S) | Quản trị: quản lý tài khoản, nhập danh sách SV từ CSV; danh mục môn học; hạn mức token và phút ghi âm theo lớp, theo SV; nhật ký và xử lý cờ… |
| C2-19 | Long | 2 (S) | Thông báo trong ứng dụng (kênh user:{id}) và email |
| KT-08 | Quyền | 1 (M) | Test bảo mật và phân quyền: JWT hết hạn, băm mật khẩu, SV không xem được kết quả của nhau, chỉ GV của lớp xem dữ liệu có tên, đồng ý ghi âm |
| KT-14 | Quyền | 2 (S) | Test vòng 2: phiên bản cây, TTS, đếm giờ, hồ sơ SV, cấu hình, trình chiếu, ưu tiên nút nghẽn, điều chỉnh cặp, quản trị, thông báo; responsiv… |
| GD-04 | Thắng | 1 (M) | Đăng nhập, quên mật khẩu, hồ sơ; SV-01 Danh sách lớp và nhập mã tham gia |
| GD-15 | Thắng | 2 (S) | Màn quản trị (bổ sung, chưa có trong Bảng 5.12): tài khoản và nhập CSV, danh mục môn, cấu hình nhà cung cấp AI, hạn mức, nhật ký và cờ vi ph… |
