# Dữ liệu mẫu (chủ: Quyền – KT-02)

| Tệp | Nội dung | Nguồn |
|---|---|---|
| `users.json` | 1 GV, 1 QTV, 30 SV (tên giả) | Mục 7.5 đề cương; tên An/Châu/Hà/Dũng/Khang cho ví dụ ghép cặp Hình 6.11 |
| `class.json` | Môn CTDL&GT, lớp "CTDL&GT – Nhóm 02", mã tham gia `CTDL2026` | Figma GV-01/GV-02 |
| `tree_ctdl_gt.json` | Cây 11 nút, 13 cạnh; rubric đầy đủ cho N5 Con trỏ | Hình 2.2, Bảng 6.1 |
| `syllabi/` | 3–5 giáo trình mẫu (PDF số, DOCX, 1 bản quét) | Quyền chuẩn bị – KT-02 |

Nạp bằng một lệnh (sau khi có C2-06/C2-07): `docker compose exec api python -m scripts.seed` – script do KT-02 viết,
đọc đúng schema `backend/app/models/schemas/tree.py` (camelCase).

> Mọi tên, MSSV là dữ liệu minh họa, không phải người thật.
