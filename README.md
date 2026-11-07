# Whybi AI

**Đội WhyBloom – Hackathon SGU 2026–2027** · *“Hỏi ‘Tại sao’ để tri thức nở rộ.”*

Nền tảng học tập **“Sinh viên làm thầy, AI làm học trò”**: thay vì để AI giải bài hộ, sinh viên giảng lại một khái niệm
cho một AI “học trò tò mò” và phải đứng vững trước câu hỏi phản biện mới được tính là *Đạt*.

| Mắt xích | Làm gì |
|---|---|
| **MX1 – Cây kỹ năng** | GV tải giáo trình → AI trích khái niệm, quan hệ tiên quyết (DAG) và rubric → GV kéo thả chỉnh sửa, phát hành |
| **MX2 – Giảng lại cho AI** | SV giảng bằng giọng nói / văn bản; Tutee hỏi vặn, Judge chấm 5 tiêu chí, Guard chống gian lận |
| **MX3 – Bản đồ nhiệt lớp** | Ma trận SV × Nút cập nhật thời gian thực, cảnh báo điểm nghẽn gốc “Nên giảng lại X” |
| **MX4 – Ghép cặp bạn cùng tiến** | Ghép bù trừ hai chiều (max-weight matching), học cặp xong giảng lại để xác nhận |

## Kiến trúc

Modular monolith + worker nền + bus sự kiện (đề cương mục 5.1, Bảng 5.15):

```
nginx ─┬─ frontend (React 19 + Vite + Tailwind, build tĩnh)
       └─ api (FastAPI, uvicorn ×4, REST /api/v1 + WebSocket /api/v1/ws)
             ├─ postgres 16 + pgvector     ├─ redis 7 (Celery broker + Pub/Sub)
             ├─ minio (kho S3 – RustFS)    └─ stt faster-whisper (tùy chọn, profile "stt")
          worker (Celery: documents · aggregation · matching · ai) · beat
```

## Chạy nhanh

Yêu cầu: Docker Desktop (Compose v2).

```bash
cp .env.example .env              # LLM_MODE=fake mặc định – chạy được không cần khóa API
docker compose up -d --build
curl http://localhost/health      # {"status":"ok",...}
```

| Địa chỉ | Nội dung |
|---|---|
| http://localhost | Frontend (mục lục màn hình khi đang phát triển) |
| http://localhost:8000/docs | OpenAPI / Swagger |
| http://localhost:9001 | Console kho tệp (S3) |

## Vibe coding cùng AI

Cả đội làm với Claude Code theo **[docs/vibe-coding.md](docs/vibe-coding.md)**: cài đặt lần đầu, 12 plugin dùng chung
(khai báo trong `.claude/settings.json` – mở repo bằng `claude` và đồng ý cài), lệnh `/trangthai` `/the` `/kiemtra` `/xong` `/pr` `/sualoi`,
mẫu prompt theo vai. Luật chung: [AGENTS.md](AGENTS.md); luật riêng: `backend/AGENTS.md`, `frontend/AGENTS.md`, `e2e/AGENTS.md`.

## Phát triển

```bash
# backend – Python 3.11–3.13, uv
cd backend
uv sync
docker compose up -d postgres redis minio
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run pytest -q && uv run ruff check .

# frontend – Node 24
cd frontend
npm ci
npm run dev                       # http://localhost:5173, proxy /api → :8000
npm run gen:api                   # sinh kiểu TypeScript từ OpenAPI của backend
npm run typecheck && npm test && npm run build

# e2e – Playwright
cd e2e && npm install && npm run install:browsers && npm test
```

## Cấu trúc repo

```
backend/        FastAPI: app/{api,ai,algorithms,services,models,workers,realtime,core,db}, alembic/, tests/
frontend/       React: src/{pages,components,layouts,lib,styles}, screens.ts (danh mục 26 màn)
nginx/          reverse proxy + build frontend
seed/           dữ liệu mẫu: 1 GV, 1 QTV, 30 SV, lớp CTDL&GT – Nhóm 02, cây 11 nút
evals/          bộ đánh giá AI (Bảng 7.3): tree, judge, guard, tutee, stt, perf
e2e/            Playwright
scripts/        tạo issue / nhãn, giả lập 30 SV, nạp seed
docs/
  spec/         đặc tả theo mô-đun + đề cương đầy đủ (outline/)
  cards/        73 thẻ việc 24 giờ (C1, C2, GD, KT)
  status/       trạng thái từng người – cập nhật sau mỗi thẻ
  design/       token, danh sách màn, ảnh Figma
  diagrams/     87 biểu đồ PlantUML (+ png/)
  checklist-h0.md · demo-script.md
  vibe-coding.md  hướng dẫn làm việc với AI, plugin, lệnh của đội
AGENTS.md       luật làm việc với AI cho cả đội (CLAUDE.md trỏ tới đây; mỗi thư mục chính có AGENTS.md riêng)
.claude/        plugin dùng chung (settings.json), lệnh /…, subagent kiem-kien-truc, hook format
.vscode/        extension gợi ý + cài đặt editor chung
```

## Đội

| Thành viên | Vai | Thẻ |
|---|---|---|
| Đăng | Trưởng nhóm · Code chính 1 – AI | [C1](docs/cards/dang.md) |
| Long | Code chính 2 – Nền tảng, gác merge `main` | [C2](docs/cards/long.md) |
| Thắng | Giao diện & slide | [GD](docs/cards/thang.md) |
| Quyền | Kiểm tra bug & demo | [KT](docs/cards/quyen.md) |

Quy trình: một thẻ = một issue = một nhánh = một PR – xem [AGENTS.md](AGENTS.md).

## Giấy phép

[MIT](LICENSE)
