# API và thời gian thực

> Gốc: mục 5.4 – [outline/05-thiet-ke.md](outline/05-thiet-ke.md) (5.4.1 quy ước, 5.4.2 Bảng 5.10, 5.4.3 Bảng 5.11, 5.4.4 ví dụ).

- Tiền tố `/api/v1`, JSON camelCase, JWT `Authorization: Bearer`, lỗi thống nhất `{"error": {"code", "message", "details"}}`.
- Khung đã có đủ 28 endpoint trong `backend/app/api/*.py`, hiện trả **501 NOT_IMPLEMENTED** kèm mã thẻ phụ trách.
  Kiểm tra hợp đồng: `backend/tests/test_api_contract.py`.
- OpenAPI: http://localhost:8000/docs (dev) · frontend sinh kiểu: `cd frontend && npm run gen:api`.
- WebSocket: `GET /api/v1/ws`, gửi `{"action":"subscribe","channel":...,"token":...}`; kênh `job:{jobId}`,
  `class:{id}:heatmap`, `user:{id}`, `session:{id}` – xem `frontend/src/lib/ws.ts`, `backend/app/realtime/`.

## Ba hợp đồng chốt giờ đầu (kế hoạch §3.1)

| Hợp đồng | File | Người chốt |
|---|---|---|
| Cây kỹ năng: Node, Edge, Rubric, TreeVersion | `backend/app/models/schemas/tree.py` | Long |
| Phiên: SessionStart, Turn, Question, JudgeResult, SessionResult | `backend/app/models/schemas/session.py` | Đăng + Long |
| LLM Adapter `call_json(schema, messages)` | `backend/app/ai/gateway.py` | Đăng |

## Luồng sự kiện (kế hoạch §3.2)

```
session (Đăng)   → session.completed(SessionResult)  [Redis Pub/Sub]
mastery (Long)   → cập nhật ma trận → mastery.changed
heatmap (Long)   → tính màu, truy vết gốc → WebSocket class:{id}:heatmap → GV-05
matching (Long)  → đọc ma trận qua MasteryService
```

Không phần nào truy vấn thẳng bảng của phần khác – gọi service hoặc nghe sự kiện.
