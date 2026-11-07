# Mô hình dữ liệu

> Gốc: mục 5.2 – [outline/05-thiet-ke.md](outline/05-thiet-ke.md) (ERD Hình 5.4–5.7, Bảng 5.2 danh sách bảng, 5.2.4 từ điển dữ liệu).

- 30 bảng, cài trong `backend/app/models/{users,tree,session,peer}.py`; enum ở `models/enums.py`.
- Migration đầu: `backend/alembic/versions/20261014_1af58d747696_initial_schema_30_tables.py`
  (bật `vector`, chỉ mục HNSW cho `document_chunks.embedding`). **Chỉ Long tạo migration** (§8.3).
- Ràng buộc DAG (5.2.5): kiểm tra chu trình ở tầng ứng dụng (`app/algorithms/dag.py`) trước khi ghi `prerequisite_edges`.
- Ma trận thành thạo (5.2.6): bảng `mastery_records` (SV × nút) – nguồn sự thật cho MX3/MX4, chỉ ghi qua `MasteryService` (`app/services/mastery.py`); thống kê theo nút ở `class_node_stats`.
- Tệp (5.2.7): giáo trình, ghi âm lưu ở kho S3 (`S3_ENDPOINT`, bucket `S3_BUCKET`); vector ở pgvector.

```bash
cd backend
uv run alembic upgrade head      # áp schema
uv run alembic check             # model ↔ migration khớp
uv run alembic revision --autogenerate -m "mô tả"   # chỉ Long
```
