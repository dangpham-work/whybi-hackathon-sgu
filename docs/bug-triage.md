# Phân loại bug (KT-01 – chủ: Quyền)

> Áp dụng cho mọi lỗi tìm thấy trên bản deploy chung hoặc local. Mẫu issue: `.github/ISSUE_TEMPLATE/bug.yml`.
> Nhãn đã tạo bằng `scripts/setup_labels.sh` (không tạo lại): `bug`, `P0`/`P1`/`P2`, `mod:<module>`.

## 1. Báo bug

1. Mở issue bằng mẫu **🐞 Bug** (GitHub → Issues → New issue). Điền đủ: mức độ, module, bước tái hiện, môi trường, kết quả mong đợi / thực tế.
2. Tiêu đề: `[P1][session] Judge trả Đạt khi thiếu tiêu chí 3`.
3. Trùng bug cũ → bình luận vào issue cũ, không mở mới.

## 2. Phân loại (Quyền, trong 10 phút sau khi issue mở)

- Gắn nhãn mức `P0`/`P1`/`P2` và nhãn `mod:<module>` theo bảng dưới; giao (assign) cho chủ thư mục theo `AGENTS.md`.
- Không tái hiện được → hỏi thêm người báo; sau 1 giờ vẫn không tái hiện được → đóng, ghi lý do.

| Mức | Khi nào | Phản hồi | Sửa xong trong | Ai xử lý |
|---|---|---|---|---|
| **P0** | Hỏng một bước của kịch bản demo 7 phút (`docs/demo-script.md`) hoặc sập bản deploy | Ngay lập tức, báo kênh #blocker | ≤ 30 phút; cả đội dừng việc đang làm nếu cần | Chủ module + Long (gác merge) |
| **P1** | Sai dữ liệu, sai quyền, lỗi hiển thị nặng, không đúng đặc tả | Trong 15 phút | 1–2 giờ | Chủ module |
| **P2** | Lỗi giao diện nhỏ, chữ, căn lề | Trong vòng làm việc | Khi rảnh; trước khóa code H20 nếu kịp | Chủ module |

Module → chủ: `session`, `voice`, `documents` → Đăng · `skilltree`, `mastery`, `heatmap`, `matching`, `admin`, `infra` → Long ·
`frontend` → Thắng · `eval` → Quyền.

## 3. Sửa và đóng

1. Người sửa dùng `/sualoi <số>`: nhánh `fix/<số>`, viết test tái hiện trước rồi mới sửa.
2. PR ghi `Closes #<số>`; Long merge khi CI xanh.
3. Quyền kiểm lại trên bản deploy sau khi merge; còn lỗi → mở lại issue.
4. Từ H19 trở đi chỉ nhận sửa P0/P1 (mục tiêu: không còn P0 mở ở H19).

## 4. Bảng GitHub Projects (tạo tay)

Token dùng cho agent chưa có quyền `project`, nên bảng chưa được tạo. Một người có quyền admin repo làm một lần:

1. Cách A – giao diện web: GitHub → tab **Projects** của tổ chức / tài khoản → **New project** → mẫu **Board**, tên `Whybi AI – Hackathon`.
   Cách B – CLI: `gh auth refresh -s project` rồi `gh project create --owner <owner> --title "Whybi AI – Hackathon"`.
2. Cột trạng thái (trường *Status*): `Todo` · `In progress` · `In review` · `Done`; thêm cột `Bug` đặt đầu bảng.
3. Thêm trường tùy chỉnh: `Mức` (single select P0/P1/P2), `Vòng` (1/2/3), `Giờ` (text, vd. H2–H3).
4. **Workflows** của bảng: bật *Auto-add to project* với bộ lọc `is:issue label:card,bug` cho repo `whybi-ai`;
   bật *Item closed → Done* và *Pull request merged → Done*.
5. Tạo view **Bug** lọc `label:bug`, nhóm theo `Mức`, sắp theo ngày mở.
6. Liên kết bảng với repo: Settings của bảng → *Manage access* / repo → tab Projects → *Link a project*.
