# Vibe coding cùng nhau – hướng dẫn cho cả đội WhyBloom

> Đây là **repo thực hành**: dựng thử sản phẩm Whybi AI trước ngày thi, tập quy trình “một thẻ – một nhánh – một PR” với AI.
> Đọc file này một lần; sau đó mỗi phiên chỉ cần `/trangthai <tên>` → `/the <mã>` → … → `/xong <mã>` → `/pr`
> (Codex: cùng các bước đó nhưng gọi bằng `$`: `$trangthai <tên>` → `$the <mã>` → … → `$pr`).

## 1. Cài đặt lần đầu (mỗi người, ~20 phút)

Cả đội làm **cùng một quy trình**, chỉ khác công cụ AI:

| Người | Công cụ AI | Gọi lệnh đội |
|---|---|---|
| Đăng, Long | Claude Code | `/the C1-05` |
| Thắng, Quyền | Codex (CLI hoặc desktop) | `$the GD-05` |

**Một lệnh cài đặt** – chạy ở gốc repo sau khi clone, và chạy lại mỗi khi pull thấy `.claude/` đổi:

```bash
uv run --no-project python scripts/setup_ai.py --ten <dang|long|thang|quyen>
#   --bo-phu-thuoc   bỏ uv sync / npm ci     --cong-cu codex|claude   đổi công cụ
```

Script kiểm công cụ, danh tính Git, `gh auth`, tạo `.env` từ `.env.example` (không đụng `.env` đã có), chạy `uv sync` + `npm ci`, bật git hook của đội rồi cài plugin:

- **Claude Code**: cài các plugin trong `.claude/settings.json`; lệnh `/trangthai /the /kiemtra /xong /pr /sualoi` và agent `kiem-kien-truc` có sẵn trong `.claude/`.
- **Codex**: thêm kho `claude-plugins-official` rồi cài cùng bộ plugin (trừ LSP và `claude-md-management` – chỉ chạy được trên Claude); sinh skill `$trangthai $the $kiemtra $xong $pr $sualoi $kiem-kien-truc` vào `.agents/skills/` từ đúng các file `.claude/commands/`. Codex tự đọc `AGENTS.md`, nên luật dự án giống hệt.
- **Git hook** (`.githooks/`, áp cho mọi công cụ): chặn commit `.env` / file khóa / chuỗi giống khóa API; dòng đầu commit phải có mã thẻ (`C1-05: …`, `fix #12: …`, `chore: …`).

Việc script **không làm thay** (làm tay một lần):

| Việc | Lệnh | Kiểm tra |
|---|---|---|
| Công cụ còn thiếu | Git, Docker Desktop, Node 24, [uv](https://docs.astral.sh/uv/), `gh`, Claude Code **hoặc** Codex | script báo `THIẾU` |
| Danh tính Git | `git config user.name "<Tên>"` · `git config user.email "<email GitHub của mình>"` | `git config user.email` |
| GitHub | `gh auth login` (GitHub.com → HTTPS → trình duyệt) | `gh auth status` |
| Khóa AI thật (khi cần) | điền vào `.env`, giữ `LLM_MODE=fake` nếu chưa có | **Không commit `.env`** |
| Chạy thử | `docker compose up -d --build` | `curl http://localhost/health` → `"status":"ok"` |
| LSP cho Claude (Đăng, Long) | `npm i -g pyright typescript typescript-language-server` | `pyright --version` |
| Mở công cụ | `claude` hoặc `codex` ở gốc repo → tin cậy thư mục | Claude: `/plugin` · Codex: `/skills` thấy skill đội |
| Đăng nhập Figma (Thắng, ai cần) | Claude: `/mcp` → `figma` → Authenticate · Codex: `codex mcp login figma` | hỏi “whoami trên figma” |

Lỗi plugin không tự cài – Claude: `/plugin marketplace add anthropics/claude-plugins-official` rồi `/plugin install <tên>@claude-plugins-official`;
Codex: `codex plugin marketplace add https://github.com/anthropics/claude-plugins-official.git` rồi `codex plugin add <tên>@claude-plugins-official`.

**Codex và Git**: khi sandbox chặn `git commit` / `git push` / `gh`, Codex sẽ xin quyền – đồng ý cho đúng lệnh đó. Không cho Codex chạy `gh pr merge` hay `--admin` (chỉ Long merge).

## 2. Plugin dùng chung (khai báo trong `.claude/settings.json`)

| Plugin | Dùng để | Ai dùng nhiều | Cách gọi |
|---|---|---|---|
| **context7** | Tra tài liệu mới nhất của thư viện (FastAPI, SQLAlchemy 2, React 19, Tailwind 4, @xyflow/react…) – tránh AI viết theo API cũ | Mọi người | thêm “**use context7**” vào prompt |
| **commit-commands** | Commit / push / tạo PR nhanh | Mọi người | `/commit`, `/commit-push-pr` (vẫn phải theo quy ước mã thẻ) |
| **code-review** | Review PR nhiều tác tử, có chấm độ tin cậy | Long (gác merge) | `/code-review` trên nhánh PR |
| **pr-review-toolkit** | Tác tử review chuyên sâu: test, xử lý lỗi, kiểu dữ liệu, comment | Long, Đăng | `/review-pr` |
| **claude-md-management** | Giữ `AGENTS.md` / `CLAUDE.md` gọn, đúng, cập nhật bài học | Long | `/revise-claude-md` cuối ngày |
| **pyright-lsp** | AI thấy lỗi kiểu Python ngay khi sửa | Đăng, Long, Quyền | tự động (cần bước 8) |
| **typescript-lsp** | AI thấy lỗi TypeScript ngay khi sửa | Thắng | tự động (cần bước 8) |
| **figma** | Đọc thiết kế, token, chụp màn từ Figma → code | Thắng | “dựng màn SV-04 theo Figma node … trong `src/screens.ts`” |
| **frontend-design** | Giao diện đẹp, chuẩn production khi chưa có Figma | Thắng | “dùng frontend-design để …” |
| **playwright** | AI mở trình duyệt thật, bấm thử, chụp màn, viết e2e | Quyền, Thắng | “mở http://localhost/gv/classes và kiểm tra …” |
| **security-guidance** | Cảnh báo lỗi bảo mật khi AI sửa code (JWT, upload file, prompt injection) | Mọi người (tự chạy) | tự động |
| **mattpocock-skills** | Kỹ năng TDD, hỏi vặn yêu cầu, viết spec/ticket, review | Mọi người | skill `tdd`, `grill-me` (hỏi vặn yêu cầu), `diagnosing-bugs`, `to-spec`, `resolving-merge-conflicts` |

Không muốn một plugin trên máy mình: tắt trong `.claude/settings.local.json` (không commit):
`{ "enabledPlugins": { "security-guidance@claude-plugins-official": false } }`.
Thêm / bỏ plugin cho **cả đội** → nhắn nhóm, Long sửa `.claude/settings.json` qua PR (Codex lấy cùng danh sách này khi chạy lại `setup_ai.py`).

### 2b. Tình huống → plugin (AI tự gọi, không chờ nhắc)

Luật repo (`AGENTS.md`, vòng `/the` → `/kiemtra` → `/xong` → `/pr`) luôn thắng quy trình riêng của plugin. Không plugin nào được merge, `--admin` hay tự duyệt.

| Tình huống | Dùng |
|---|---|
| Gọi thư viện (FastAPI, SQLAlchemy 2, Pydantic, React 19, Tailwind 4, Vitest, Playwright…) | **context7** – không đoán API |
| Bắt đầu thẻ / viết test theo “Xong khi” | skill **tdd** – test đỏ trước |
| Yêu cầu mơ hồ, thẻ thiếu tiêu chí | skill **grill-me** |
| Lỗi / test đỏ không rõ nguyên nhân | skill **diagnosing-bugs**; bug có issue → `/sualoi` |
| Xung đột merge / rebase | skill **resolving-merge-conflicts** (file hợp đồng → gọi chủ hợp đồng) |
| Trước khi commit | **kiem-kien-truc** |
| Trước khi mở PR | **pr-review-toolkit** (`code-reviewer`; thêm `silent-failure-hunter` khi có try/except, `pr-test-analyzer` khi thêm logic) |
| Rà PR người khác (Long) | **code-review** – chỉ comment |
| Code đụng JWT, mật khẩu, upload, ghi âm, prompt LLM | **security-guidance** (tự chạy) |
| Màn có Figma / chưa có Figma | **figma** / **frontend-design** |
| Kiểm giao diện thật, e2e | **playwright** (`http://localhost`, `LLM_MODE=fake`) |

## 3. Lệnh của đội (`.claude/commands/` – Codex dùng bản sinh trong `.agents/skills/`)

| Claude Code | Codex | Khi nào |
|---|---|---|
| `/trangthai <tên>` | `$trangthai <tên>` | Đầu phiên: ai đang làm gì, ai chờ ai, gợi ý thẻ tiếp theo |
| `/the <mã>` | `$the <mã>` | Bắt đầu thẻ: nạp thẻ + đặc tả + trạng thái, lập kế hoạch (> 3 file thì chờ duyệt) |
| `/kiemtra` | `$kiemtra` | Bất cứ lúc nào: chạy ruff / pytest / typecheck / vitest / build cho phần đã đổi |
| `/xong <mã>` | `$xong <mã>` | Kết thúc thẻ: đối chiếu “Xong khi”, rà kiến trúc, cập nhật `docs/status/`, đề xuất commit |
| `/pr [số issue]` | `$pr [số issue]` | Rebase, kiểm tra, push, mở PR theo mẫu |
| `/sualoi <số issue>` | `$sualoi <số issue>` | Sửa bug: test tái hiện trước, nhánh `fix/<số>` |

Rà kiến trúc **`kiem-kien-truc`**: Claude dùng subagent trong `.claude/agents/` (“dùng kiem-kien-truc rà nhánh này”); Codex dùng skill `$kiem-kien-truc`.
Sửa lệnh: chỉ sửa `.claude/commands/` rồi chạy lại `setup_ai.py` – không sửa tay `.agents/skills/`.

## 4. Vòng làm một thẻ

```text
git switch main && git pull --rebase origin main
claude
  /trangthai long            → chọn thẻ, ví dụ C2-03
  /the C2-03                 → đọc kế hoạch, sửa nếu cần, gõ "ok làm đi"
  (AI viết test trước → code → chạy test)
  /kiemtra
  /xong C2-03                → đồng ý commit
  /pr 12
```

Quy tắc vàng:

1. **Một phiên = một thẻ.** Xong thẻ → `/clear` trước khi sang thẻ mới (ngữ cảnh sạch = AI ít bịa).
2. **Đọc kế hoạch trước khi cho AI code.** Sai hướng ở bước kế hoạch rẻ hơn 10 lần sửa code.
3. **Test là hợp đồng.** Yêu cầu AI viết test theo “Xong khi” trước; không chấp nhận “đã sửa” khi test chưa chạy.
4. **Không cho AI sửa thư mục người khác.** AI đề xuất đụng file ngoài phạm vi → dừng, nhắn chủ thư mục.
5. **Không bí mật trong chat / code.** Khóa API chỉ ở `.env`. Lỡ dán token vào chat → thu hồi ngay.
6. **Kẹt 2–3 vòng không xong → dừng**, cắt thẻ nhỏ hơn hoặc hỏi người (kênh #blocker sau 20 phút).
7. **Commit nhỏ, thường xuyên.** Code sinh hàng loạt (scaffold) commit riêng và ghi rõ trong message.

## 5. Mẫu prompt theo vai

**Đăng – AI (C1)**
- “/the C1-05. Judge chấm 5 tiêu chí theo BR-03, viết test với gateway fake trước. use context7 cho pydantic v2.”
- “Viết 10 ca tấn công prompt injection mới cho `evals/guard/attacks.jsonl` theo Phụ lục B, đừng sửa code.”

**Long – nền tảng (C2)**
- “/the C2-03. Thêm/xóa cạnh qua `algorithms/dag.py`, trả `AppError(409, "CYCLE_DETECTED")` kèm đường đi chu trình.”
- “/code-review PR #14 – tập trung vào cô lập dữ liệu giữa mô-đun và MasteryService.”

**Thắng – giao diện (GD)**
- “Dựng màn SV-02 theo Figma node trong `src/screens.ts`, dùng `SkillTree` và token màu có sẵn; trạng thái nút lấy từ `MASTERY` trong `lib/status.ts`.”
- “Mở http://localhost/sv/classes bằng playwright ở khổ 375px, chụp màn và liệt kê chỗ vỡ bố cục.”

**Quyền – kiểm thử & demo (KT)**
- “/the KT-03. Dựng khung e2e chạy trong CI; viết spec cho bước 1–4 trong `docs/demo-script.md`, chọn phần tử bằng getByRole.”
- “Chạy `evals/run.py guard` và điền bảng kết quả vào `evals/results/guard.md`.”

## 6. Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| AI dùng API cũ (React Router v6, SQLAlchemy 1.x, Tailwind 3 `tailwind.config.js`) | Nhắc “use context7”, chỉ rõ phiên bản trong `package.json` / `pyproject.toml` |
| AI tạo file trùng chức năng | Chỉ cho nó file đã có (bảng “Bản đồ thư mục” trong `backend/AGENTS.md`, `frontend/AGENTS.md`) |
| AI sửa test cho xanh thay vì sửa code | Từ chối; yêu cầu giải thích vì sao test sai trước |
| Plugin LSP báo lỗi không tìm thấy server | Làm bước 8 rồi khởi động lại Claude Code |
| `docker compose up` chậm / lỗi mạng | `docker compose up -d --build api` trước (worker, beat dùng lại image `whybi-backend:dev`) |
| Figma MCP không kết nối | `/mcp` → `figma` → Authenticate lại; kiểm tra đã đăng nhập Figma trên trình duyệt |
| Xung đột merge ở file hợp đồng | Không tự giải quyết – gọi chủ hợp đồng (bảng trong `AGENTS.md`) |

## 7. Chi phí và ngữ cảnh

- Ngữ cảnh dài làm AI chậm và kém: `/clear` sau mỗi thẻ, `/compact` khi phiên quá dài.
- Không bảo AI “đọc cả đề cương” – dùng file tóm lược trong `docs/spec/` của phần mình.
- Kiểm thử tải và chạy thử luôn dùng `LLM_MODE=fake`; chỉ bật `real` khi cần kiểm chất lượng prompt.
