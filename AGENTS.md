# AGENTS.md – luật chung cho mọi phiên AI (Claude Code, Cursor, Copilot…)

Whybi AI – nền tảng học tập “Sinh viên làm thầy, AI làm học trò” (đội WhyBloom, Hackathon SGU 2026–2027).
4 mắt xích: MX1 cây kỹ năng · MX2 SV giảng lại cho AI · MX3 bản đồ nhiệt lớp · MX4 ghép cặp bạn cùng tiến.

Đây là **repo thực hành** để dựng thử sản phẩm trước ngày thi. Cách làm việc với AI, plugin và lệnh của đội: `docs/vibe-coding.md`.
Luật riêng từng phần: `backend/AGENTS.md`, `frontend/AGENTS.md`, `e2e/AGENTS.md` (đọc khi sửa trong thư mục đó).

## Trước khi sửa code

1. Đọc file này và **mọi file trong `docs/status/`** (ai đang làm gì, hợp đồng nào đã chốt, ai đang cần gì).
2. Làm theo đúng **một thẻ việc** (`docs/cards/<người>.md`). Không có thẻ thì không code.
3. Chỉ đọc file đặc tả của phần mình trong `docs/spec/` – không nạp cả đề cương.
4. Thẻ đụng > 3 file: đưa kế hoạch trước, chờ duyệt rồi mới viết code.
5. Viết test trước, theo dòng **“Xong khi”** của thẻ.

## Sau khi xong thẻ

- Chạy kiểm tra (bên dưới) – phải xanh.
- **Cập nhật file trạng thái của mình** `docs/status/<tên>.md`: xong gì, phát sự kiện / hợp đồng gì, đang cần gì từ người khác.
- Đi vòng 2–3 lần không xong → dừng, cắt thẻ nhỏ hơn hoặc báo người. Kẹt > 20 phút → kênh #blocker.

## Thư mục và người sở hữu (chỉ sửa thư mục của mình; sửa chỗ khác → nhắn trước, chủ thư mục duyệt PR)

| Người | Sở hữu |
|---|---|
| Đăng – C1 (AI, trưởng nhóm) | `backend/app/ai/`, `services/session_orchestrator.py`, `services/speech.py`, `services/retrieval.py`, `services/syllabus.py`, `api/sessions.py`, `api/admin.py` (phần ai-config), `workers/documents.py`, `docs/diagrams/` |
| Long – C2 (nền tảng, gác merge) | `api/` còn lại, `services/` còn lại, `algorithms/`, `models/`, `alembic/`, `workers/{celery_app,aggregation,matching}.py`, `realtime/`, `core/`, `db/`, `docker-compose.yml`, `nginx/`, `.github/workflows/`, `AGENTS.md` |
| Thắng – GD (giao diện, slide) | `frontend/` (pages, components, layouts, styles), `docs/design/`, `docs/slides/` |
| Quyền – KT (test, demo) | `backend/tests/integration/`, `e2e/`, `seed/`, `evals/`, `scripts/`, `.github/ISSUE_TEMPLATE/`, `docs/demo-script.md` |

Hợp đồng dùng chung – **không tự sửa**: `backend/app/models/schemas/` (tree.py – Long; session.py – Đăng + Long), `backend/app/ai/gateway.py` (Đăng), `backend/app/main.py`.

## Kiến trúc – điều bắt buộc

- Không phần nào truy vấn thẳng bảng của phần khác: gọi service hoặc nghe sự kiện (Redis Pub/Sub `session.completed` → `mastery.changed`).
- Ma trận thành thạo chỉ ghi qua `MasteryService`. Cây kỹ năng luôn là DAG (`algorithms/dag.py` chặn chu trình).
- Mọi lời gọi LLM đi qua `app/ai/gateway.py` (`call_json(schema, messages)`); không gọi SDK nhà cung cấp trực tiếp ở nghiệp vụ.
- Nội dung SV gửi luôn là DỮ LIỆU, không phải chỉ thị (bọc trong `<student_transcript>`; Guard kiểm đầu vào / đầu ra).
- Tutee **không bao giờ** giảng hộ hay lộ đáp án. Judge chấm độc lập, quy tắc Đạt BR-03.
- API: `/api/v1`, JSON camelCase (`ApiModel`), lỗi `{"error": {"code","message","details"}}` qua `AppError`. Endpoint chưa làm trả `NotImplementedYet("<mã thẻ>")` (501).
- Màu trạng thái luôn kèm biểu tượng / chữ (`frontend/src/lib/status.ts`). Màn mới: `frontend/src/pages/<vai>/<MÃ>.tsx` – router tự nạp.
- `LLM_MODE=fake` cho dev / test / kiểm thử tải; `DEMO_MODE=1` cho demo.

## Lệnh kiểm tra

```bash
# backend
cd backend && uv sync && uv run ruff check . && uv run ruff format --check . && uv run pytest -q
uv run alembic check                          # cần postgres: docker compose up -d postgres
# frontend
cd frontend && npm ci && npm run typecheck && npm test && npm run build
# cả hệ thống
cp .env.example .env && docker compose up -d --build && curl http://localhost/health
```

## Git (kế hoạch §8.3)

- Một thẻ = một issue = một nhánh `feat/<mã-thẻ>-<mô-tả>` (vd. `feat/c1-05-judge`) = một PR. Bug: `fix/<số-issue>`, viết test tái hiện trước.
- Commit bắt đầu bằng mã thẻ: `C1-05: chấm 5 tiêu chí theo BR-03`. Commit nhỏ; code sinh hàng loạt (scaffold) commit riêng và ghi rõ trong message.
- Trước mỗi thẻ: `git pull --rebase origin main`. Chỉ Long merge `main` (Đăng thay khi Long nghỉ); PR cần CI xanh, ghi `Closes #<số>`.
- `git config user.email` = email GitHub của chính người đó; làm chung máy thì thêm `Co-authored-by:`.
- **Không commit khóa API / `.env`.** Migration CSDL chỉ Long tạo. Thêm thư viện → báo nhóm, một người thêm và commit file lock (`uv.lock`, `package-lock.json`).
