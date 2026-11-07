# Test tích hợp (chủ: Quyền – KT-03)

pytest + httpx gọi API thật (docker compose hoặc job `e2e` trong CI) – Postgres/Redis thật, `LLM_MODE=fake`.
Test case nguồn: Bảng 7.2 (TC01–TC16) và Phụ lục B của đề cương.

```bash
docker compose up -d --build                                  # ở gốc repo
cd backend
uv run pytest -q                                              # test gắn mark integration bị BỎ QUA
RUN_INTEGRATION=1 uv run pytest -q -m integration             # chạy trên http://localhost:8000
RUN_INTEGRATION=1 INTEGRATION_API_URL=https://<máy> uv run pytest -q -m integration
```

- Test cần stack: gắn `pytestmark = pytest.mark.integration` (hoặc `@pytest.mark.integration`), dùng fixture
  `http` (gốc API: `/health`, `/openapi.json`) hoặc `api` (đã có `/api/v1`) trong `conftest.py`.
- Đã bật `RUN_INTEGRATION=1` mà API không trả lời `/health` → test **fail** (không bỏ qua) để CI thấy stack hỏng.
- Lỗi đã biết nhưng chưa sửa: `@pytest.mark.xfail(reason="<mã thẻ>: …")`, không xóa test.
- Test không cần Docker (vd. `test_seed_data.py` của KT-02) không gắn mark, chạy trong `pytest -q` bình thường.
