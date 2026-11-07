# backend/ – hướng dẫn cho phiên AI

> Bổ sung cho `AGENTS.md` ở gốc (luật chung vẫn áp dụng). Python 3.11 · FastAPI · SQLAlchemy 2 · Alembic · Celery · Redis · pgvector.

## Chạy

```bash
cd backend
uv sync                          # cài phụ thuộc (không pip install)
uv run pytest -q                 # test nhanh, không cần Docker (LLM_MODE=fake)
uv run ruff check . && uv run ruff format .
uv run uvicorn app.main:app --reload   # cần postgres + redis: docker compose up -d postgres redis minio
```

Thêm thư viện: `uv add <gói>` → **báo nhóm** và commit `pyproject.toml` + `uv.lock` cùng nhau.

## Bản đồ thư mục

| Thư mục | Vai trò | Ghi chú |
|---|---|---|
| `app/api/` | Router FastAPI, chỉ nhận/trả schema, gọi service | Không viết SQL ở đây. Quyền: `deps.py` (`current_user`, `require_role`) |
| `app/services/` | Nghiệp vụ, một service / mô-đun | Ghi mastery chỉ qua `services/mastery.py` |
| `app/algorithms/` | Hàm thuần (DAG, ghép cặp, nguyên nhân gốc) | Không I/O → test unit dễ |
| `app/ai/` | `gateway.py` (`call_json`), `providers/`, `agents/`, `prompts/` | Mọi lời gọi LLM qua gateway |
| `app/models/` | ORM (`tree.py`, `session.py`, `users.py`, `peer.py`) | Đổi bảng → Long tạo migration |
| `app/models/schemas/` | Pydantic – **hợp đồng chung** | Kế thừa `ApiModel` (camelCase). Không tự sửa |
| `app/realtime/` | WebSocket gateway + Redis bus | Sự kiện: `session.completed` → `mastery.changed` |
| `app/workers/` | Celery task | Hàng đợi riêng cho documents / aggregation / matching |
| `app/core/` | config, errors (`AppError`, `NotImplementedYet`), security, logging | |

## Mẫu cần theo

- Lỗi: `raise AppError(409, "CYCLE_DETECTED", "…", {"path": [...]})` (status, code, message, details) – không `HTTPException` thô.
- Endpoint chưa làm: `raise NotImplementedYet("C2-07")` (501). Khi làm thẻ, thay dòng này bằng code thật; `tests/test_api_contract.py` giữ đủ 28 endpoint Bảng 5.10 – không xóa đường dẫn.
- Gọi LLM: `get_gateway().call_json(JudgeResult, messages)` – schema đầu ra là Pydantic; `LLM_MODE=fake` trả dữ liệu mẫu hợp lệ theo schema.
- Lời SV đưa vào prompt luôn bọc `<student_transcript>…</student_transcript>` và qua Guard.
- Config đọc qua `get_settings()` trong `app/core/config.py` – không `os.getenv` rải rác.

## Test

- `tests/unit/` – hàm thuần, schema. `tests/ai/` – tác tử với gateway fake. `tests/integration/` – của Quyền (cần Docker).
- Viết test trước theo “Xong khi” của thẻ. Fixture `client` (TestClient) trong `tests/conftest.py`.
- Không gọi LLM thật trong test; không phụ thuộc thứ tự test.
