# Đặc tả (docs/spec)

Nguồn gốc: *Đề cương chi tiết – Tài liệu phân tích và thiết kế hệ thống v0.1* (đội WhyBloom), chuyển sang Markdown
theo chương trong [`outline/`](outline/). Hình là ảnh xuất từ `docs/diagrams/*.puml` (sửa `.puml` rồi xuất lại).

**Luật §4.2 kế hoạch:** không đưa cả đề cương cho AI – chỉ trỏ tới file đặc tả của phần mình.

| File | Dùng khi làm |
|---|---|
| [mx1-skill-tree.md](mx1-skill-tree.md) | MX1 – lớp, giáo trình, trích cây, rubric, trình sửa cây, phát hành, phiên bản |
| [mx2-session.md](mx2-session.md) | MX2 – phiên giảng, Tutee / Judge / Guard, STT / TTS, chống gian lận |
| [mx3-heatmap.md](mx3-heatmap.md) | MX3 – ma trận thành thạo, bản đồ nhiệt, truy vết điểm nghẽn gốc, WebSocket |
| [mx4-matching.md](mx4-matching.md) | MX4 – ghép cặp bù trừ, xác nhận lại |
| [admin.md](admin.md) | Tài khoản, xác thực, phân quyền, quản trị, cấu hình AI |
| [api.md](api.md) | Quy ước API, 28 endpoint, kênh realtime, hợp đồng dữ liệu |
| [data-model.md](data-model.md) | ERD, 30 bảng, ràng buộc DAG, ma trận thành thạo |
| [ai-agents.md](ai-agents.md) | Kiến trúc tác tử, prompt, chấm điểm, đánh giá AI |

## Đề cương đầy đủ

| Chương | File |
|---|---|
| 1. Tổng quan đề tài | [outline/01-tong-quan.md](outline/01-tong-quan.md) |
| 2. Cơ sở lý thuyết và công nghệ | [outline/02-co-so-ly-thuyet.md](outline/02-co-so-ly-thuyet.md) |
| 3. Phân tích yêu cầu (FR, NFR, BR, truy vết) | [outline/03-yeu-cau.md](outline/03-yeu-cau.md) |
| 4. Phân tích hệ thống (UC, hoạt động, tuần tự, trạng thái, lớp) | [outline/04-phan-tich.md](outline/04-phan-tich.md) |
| 5. Thiết kế hệ thống (kiến trúc, dữ liệu, API, giao diện, bảo mật, triển khai) | [outline/05-thiet-ke.md](outline/05-thiet-ke.md) |
| 6. Thiết kế lõi AI và thuật toán | [outline/06-ai-thuat-toan.md](outline/06-ai-thuat-toan.md) |
| 7. Cài đặt, kiểm thử và đánh giá | [outline/07-cai-dat-kiem-thu.md](outline/07-cai-dat-kiem-thu.md) |
| 8. Kết luận và hướng phát triển | [outline/08-ket-luan.md](outline/08-ket-luan.md) |
| Tài liệu tham khảo | [outline/09-tai-lieu-tham-khao.md](outline/09-tai-lieu-tham-khao.md) |
| Phụ lục A – Prompt mẫu | [outline/pl-a-prompt.md](outline/pl-a-prompt.md) |
| Phụ lục B – Kịch bản chống gian lận | [outline/pl-b-chong-gian-lan.md](outline/pl-b-chong-gian-lan.md) |
| Phụ lục C – Kế hoạch | [outline/pl-c-ke-hoach.md](outline/pl-c-ke-hoach.md) |
| Phụ lục D – Khai báo công cụ AI | [outline/pl-d-khai-bao-ai.md](outline/pl-d-khai-bao-ai.md) |
| Phụ lục E – Mã PlantUML | [`../diagrams/`](../diagrams/) |

## Sai khác so với đề cương (ghi lại để cập nhật bản hoàn chỉnh)

- Lưu trữ tệp: image `minio/minio` không còn phát hành trên Docker Hub → dùng **RustFS** (tương thích S3), giữ tên dịch vụ `minio`.
- Frontend build bằng Node 24 LTS (Node 20 đã hết hỗ trợ 04/2026).
