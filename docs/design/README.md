# Thiết kế giao diện

- Figma: https://www.figma.com/design/XtHQ0l4kAXNYzTb3v8iKDV/Untitled (trang *Nền tảng & Thành phần*, *GV – Web 1440×1024*, *SV – Mobile 390×844*)
- Ảnh chụp trong `screens/` xuất từ Figma ngày 14/10/2026 – xuất lại khi Figma đổi. Nền tảng & thành phần: [screens/FOUNDATION.png](screens/FOUNDATION.png).
- Đặc tả gốc: mục 5.5 – [../spec/outline/05-thiet-ke.md](../spec/outline/05-thiet-ke.md) (Bảng 5.12 danh sách màn, wireframe Hình 5.11–5.24).
- Danh mục màn hình trong code: `frontend/src/screens.ts` (đổi ở đây thì cập nhật bảng dưới). Thêm màn = tạo
  `frontend/src/pages/<lecturer|student|admin|auth>/<MÃ bỏ gạch>.tsx` có `export default` – router tự nạp.

## Token (đã khai báo ở `frontend/src/styles/index.css`)

| Nhóm | Giá trị |
|---|---|
| Font | Be Vietnam Pro |
| Chữ | ink-900 `#17202E` · ink-700 `#3D4A60` · ink-500 `#6B7A90` · ink-300 `#9AA6B8` |
| Viền / nền | line-strong `#CFD6E2` · line-soft `#E3E7EE` · bg-app `#F6F7F9` · surface `#FFFFFF` |
| Thương hiệu | honey `#F2A91B` · honey-deep `#9A6504` · honey-soft `#FFF4DC` · teal `#0B6E63` · teal-soft `#E3F2F0` |
| Trạng thái | Đạt `#C8E6C9` · Đang giảng / 40–70% `#FFF59D` · Chưa đạt `#EF9A9A` · Khóa / chưa đủ mẫu `#ECEFF1` · Cần xác nhận lại `#FFE0B2` (xem `frontend/src/lib/status.ts`) |
| Hình khối | bo góc 10px · bóng `0 3px 10px rgba(23,33,48,.05–.08)` · icon Lucide |

Màu trạng thái luôn đi kèm biểu tượng / chữ (không chỉ dựa vào màu – mục 5.5.4).

## Màn hình

| Mã | Tên | Route | Thẻ · vòng | Yêu cầu | Figma | Ảnh |
|---|---|---|---|---|---|---|
| AUTH-01 | Đăng nhập | `/login` | GD-04 · V1 | FR-AD-01 | — | — (chưa có Figma) |
| AUTH-02 | Quên mật khẩu | `/forgot-password` | GD-04 · V1 | FR-AD-01 | — | — (chưa có Figma) |
| GV-01 | Danh sách lớp | `/gv/classes` | GD-05 · V1 | FR-SK-01 | [14:699](https://www.figma.com/design/XtHQ0l4kAXNYzTb3v8iKDV/Untitled?node-id=14-699) | [ảnh](screens/GV-01.png) |
| GV-02 | Tổng quan lớp | `/gv/classes/:classId` | GD-05 · V1 | FR-SK-01 | [14:1122](https://www.figma.com/design/XtHQ0l4kAXNYzTb3v8iKDV/Untitled?node-id=14-1122) | [ảnh](screens/GV-02.png) |
| GV-03 | Tải giáo trình & tiến độ | `/gv/classes/:classId/syllabus` | GD-05 · V1 | FR-SK-02, FR-SK-03 | [14:1468](https://www.figma.com/design/XtHQ0l4kAXNYzTb3v8iKDV/Untitled?node-id=14-1468) | [ảnh](screens/GV-03.png) |
| GV-04 | Trình sửa cây & rubric | `/gv/classes/:classId/tree` | GD-09 · V1 | FR-SK-04…10 | [17:1065](https://www.figma.com/design/XtHQ0l4kAXNYzTb3v8iKDV/Untitled?node-id=17-1065) | [ảnh](screens/GV-04.png) |
| GV-05 | Dashboard bản đồ nhiệt | `/gv/classes/:classId/heatmap` | GD-10 · V1 | FR-HM-01…05, 09, 10 | [17:1447](https://www.figma.com/design/XtHQ0l4kAXNYzTb3v8iKDV/Untitled?node-id=17-1447) | — (chưa có Figma) |
| GV-06 | Chi tiết nút & điểm nghẽn | `/gv/classes/:classId/nodes/:nodeId` | GD-10 · V1 | FR-HM-06 | [19:1460](https://www.figma.com/design/XtHQ0l4kAXNYzTb3v8iKDV/Untitled?node-id=19-1460) | [ảnh](screens/GV-06.png) |
| GV-07 | Hồ sơ năng lực SV | `/gv/classes/:classId/students/:studentId` | GD-13 · V2 | FR-HM-07 | [19:1885](https://www.figma.com/design/XtHQ0l4kAXNYzTb3v8iKDV/Untitled?node-id=19-1885) | [ảnh](screens/GV-07.png) |
| GV-08 | Transcript & ghi âm | `/gv/sessions/:sessionId` | GD-13 · V2 | FR-HM-07, FR-TB-14 | [19:2212](https://www.figma.com/design/XtHQ0l4kAXNYzTb3v8iKDV/Untitled?node-id=19-2212) | [ảnh](screens/GV-08.png) |
| GV-09 | Quản lý ghép cặp | `/gv/classes/:classId/matching` | GD-11 · V1 | FR-PM-01…08 | [19:2649](https://www.figma.com/design/XtHQ0l4kAXNYzTb3v8iKDV/Untitled?node-id=19-2649) | [ảnh](screens/GV-09.png) |
| GV-10 | Cấu hình ngưỡng | `/gv/classes/:classId/settings` | GD-14 · V2 | FR-HM-08 | [19:2959](https://www.figma.com/design/XtHQ0l4kAXNYzTb3v8iKDV/Untitled?node-id=19-2959) | [ảnh](screens/GV-10.png) |
| SV-01 | Danh sách lớp / nhập mã | `/sv/classes` | GD-04 · V1 | FR-TB-01 | [25:482](https://www.figma.com/design/XtHQ0l4kAXNYzTb3v8iKDV/Untitled?node-id=25-482) | [ảnh](screens/SV-01.png) |
| SV-02 | Bản đồ học tập | `/sv/classes/:classId` | GD-06 · V1 | FR-TB-01 | [25:714](https://www.figma.com/design/XtHQ0l4kAXNYzTb3v8iKDV/Untitled?node-id=25-714) | [ảnh](screens/SV-02.png) |
| SV-03 | Chi tiết nút | `/sv/classes/:classId/nodes/:nodeId` | GD-06 · V1 | FR-TB-02 | [25:826](https://www.figma.com/design/XtHQ0l4kAXNYzTb3v8iKDV/Untitled?node-id=25-826) | [ảnh](screens/SV-03.png) |
| SV-04 | Phiên giảng lại | `/sv/sessions/:sessionId` | GD-07 · V1 | FR-TB-03…05, 08, 10, 11 | [25:1214](https://www.figma.com/design/XtHQ0l4kAXNYzTb3v8iKDV/Untitled?node-id=25-1214) | [ảnh](screens/SV-04.png) |
| SV-05 | Xác nhận bản chép lời | `/sv/sessions/:sessionId/transcript` | GD-08 · V1 | FR-TB-06, 07 | [25:1280](https://www.figma.com/design/XtHQ0l4kAXNYzTb3v8iKDV/Untitled?node-id=25-1280) | [ảnh](screens/SV-05.png) |
| SV-06 | Kết quả & phản hồi | `/sv/sessions/:sessionId/result` | GD-08 · V1 | FR-TB-13 | [25:1410](https://www.figma.com/design/XtHQ0l4kAXNYzTb3v8iKDV/Untitled?node-id=25-1410) | [ảnh](screens/SV-06.png) |
| SV-07 | Bạn cùng tiến | `/sv/classes/:classId/peers` | GD-11 · V1 | FR-PM-01, 05, 06, 07 | [25:1602](https://www.figma.com/design/XtHQ0l4kAXNYzTb3v8iKDV/Untitled?node-id=25-1602) | [ảnh](screens/SV-07.png) |
| SV-08 | Lịch sử phiên | `/sv/history` | GD-16 · V3 | FR-TB-15 | [25:1031](https://www.figma.com/design/XtHQ0l4kAXNYzTb3v8iKDV/Untitled?node-id=25-1031) | [ảnh](screens/SV-08.png) |
| ME-01 | Hồ sơ cá nhân | `/me` | GD-04 · V1 | FR-AD-01 | — | — (chưa có Figma) |
| AD-01 | Tài khoản & nhập CSV | `/admin/users` | GD-15 · V2 | FR-AD-03 | — | — (chưa có Figma) |
| AD-02 | Danh mục môn học | `/admin/courses` | GD-15 · V2 | FR-AD-04 | — | — (chưa có Figma) |
| AD-03 | Cấu hình nhà cung cấp AI | `/admin/ai-config` | GD-15 · V2 | FR-AD-05 | — | — (chưa có Figma) |
| AD-04 | Hạn mức | `/admin/quotas` | GD-15 · V2 | FR-AD-06 | — | — (chưa có Figma) |
| AD-05 | Nhật ký & cờ vi phạm | `/admin/flags` | GD-15 · V2 | FR-AD-07 | — | — (chưa có Figma) |
