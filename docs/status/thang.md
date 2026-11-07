# docs/status/thang.md   (chỉ Thắng sửa)

> Cập nhật sau mỗi thẻ (kế hoạch §4.2). Mọi người – và mọi phiên AI – đọc hết `docs/status/` trước khi sửa code.

- Xong:
  - GD-01 – khung giao diện 3 vai (PR #79)
  - GD-03 – component `SkillTree` (React Flow + dagre), dùng chung cho GV-04, GV-05, SV-02 (PR #81)
  - GD-02 – kiểu sinh từ OpenAPI (đã có schema C1-01, C2-02), lớp gọi API có kiểu, WebSocket client, trạng thái tải / lỗi dùng chung (PR #85)
  - GD-04 – AUTH-01 Đăng nhập, AUTH-02 Quên mật khẩu, ME-01 Hồ sơ, SV-01 Danh sách lớp + nhập mã 8 ký tự. Dựng theo scaffold C2-07 / C2-08, test dùng mock.
  - GD-07 – SV-04 Phiên giảng lại (`pages/student/SV04.tsx`, xếp chồng trên C1-07 #94): hội thoại, ô gõ đo dán / tốc độ gõ,
    `Recorder` (MediaRecorder ≤ 3 phút lời giảng / 90 s câu trả lời, tự dừng, hỏi đồng ý BR-13 trước khi xin micro, xử lý bị chặn micro)
    và `Waveform` (AnalyserNode). Test `src/test/sv04.test.tsx`, `src/test/typing-meter.test.ts`.
- Phát sự kiện / hợp đồng đã chốt:
  - Phiên đăng nhập ở `frontend/src/lib/auth.ts`:
    - `auth.login()` gọi `POST /auth/login`, dùng `accessToken` làm Bearer, rồi `GET /me`. Vai lấy từ `/me`, không giải mã JWT.
    - `auth.logout()` luôn xóa phiên phía trình duyệt, kể cả khi máy chủ lỗi.
    - Có thêm `useCurrentUser()`, `homeFor(role)` (GV → `/gv/classes`, SV → `/sv/classes`, QTV → `/admin/users`) và `?next=` sau đăng nhập.
  - Layout ba vai hiện tên và vai từ `/me`; chưa đăng nhập thì hiện "Khách".
  - `<AsyncView>` gặp 401 thì hiện link "Đăng nhập lại" kèm `?next=` để quay về đúng trang. `?next=` lọc qua `safeNext()` để chặn open redirect.
  - Refresh token chỉ giữ trong bộ nhớ, không ghi localStorage. Đề xuất C2-07 đặt refresh token bằng cookie httpOnly.
  - `TREE_STATUS` và `NO_TREE` trong `lib/status.ts`: huy hiệu trạng thái cây có màu, biểu tượng và chữ.
  - `SkillTree` (`frontend/src/components/SkillTree.tsx`): props `mode` (`edit` | `heatmap` | `learner`), `nodes` / `edges` (kiểu `Node` / `Edge` sinh từ OpenAPI), `mastery` / `heat` theo `key` của nút, `details`, `rootCauseKey`, `selectedKey`, `onNodeClick`, `onNodeMove`, `onConnect`.
  - Tự sắp xếp bằng `layoutTree()` (`frontend/src/lib/tree-layout.ts`, dùng dagre). Nếu mọi nút đã có `positionX/Y` thì dùng vị trí đã lưu.
  - `frontend/src/lib/api.ts`:
    - `apiCall(method, path, { path, query, body, signal })` lấy kiểu tham số, body và kết quả từ `api-types.ts`. Sai đường dẫn hoặc sai body thì `tsc` báo lỗi.
    - `ApiError { status, code, message (câu dễ hiểu), serverMessage, details, notImplemented }`.
    - `friendlyMessage(status, code)` tra theo mã lỗi, rồi theo mã HTTP, cuối cùng là câu chung. Máy chủ thêm mã lỗi mới thì báo Thắng để thêm vào `FRIENDLY`.
  - `useApi()` + `<AsyncView>`: hiện tải, lỗi (có nút Thử lại), trống, và "đang phát triển" khi gặp 501.
  - `frontend/src/lib/ws.ts`:
    - `RealtimeClient` gửi `{action: "subscribe" | "unsubscribe", channel, token}`, nhận `{channel, event, payload}`. Tin không có `channel` thì phát cho mọi người nghe.
    - Tự nối lại sau 1 → 10 s và phát sự kiện `reconnected`. Có `close()`, `onStatus()` và hook `useChannel()`.
  - Gọi API khi chưa có C2-07: đặt `VITE_DEV_TOKEN=dev-lecturer` trong `frontend/.env.local` (chỉ có tác dụng ở `npm run dev`).
  - SV-04 (GD-07):
    - Vào màn: `navigate("/sv/sessions/" + sessionId, { state: { opening, nodeTitle, inputMode } })` (kiểu `SessionLocationState`) – SV-03 (GD-06) gọi `POST /sessions` rồi chuyển sang.
    - Lượt chữ gửi `Turn{turnType, inputMode:"TEXT", text, pasteRatio, typingCps, responseTimeMs, transcriptEdited:false}`;
      `pasteRatio` = ký tự dán / (dán + gõ), `typingCps` = ký tự gõ / giây gõ thật (khoảng nghỉ cắt ở 2 s) – `lib/typing-meter.ts`.
    - Lượt giọng: `POST /sessions/{id}/audio` (multipart `file`, webm/opus) → `Transcript` → `Turn{inputMode:"VOICE", text, audioRef, sttConfidence}`.
    - `turnType`: EXPLANATION khi phiên `EXPLAINING`, ANSWER khi `CHALLENGING` (khớp orchestrator). Câu hỏi nhận từ `TurnReply.question` và `session.question` trên kênh `session:{id}`, bỏ trùng.
    - Đồng ý ghi âm giữ trong phiên màn (hỏi 1 lần mỗi phiên), không lưu trình duyệt.
    - Thêm `FRIENDLY`: `SESSION_NOT_FOUND`, `SESSION_NOT_ACTIVE`, `TOKEN_BUDGET_EXCEEDED`.
    - Lưu ý chạy test: Vitest 5 lưu cache module ở `node_modules/.vitest-cache`; thêm màn mới mà router vẫn ra trang giữ chỗ thì xóa thư mục này.
- Đang làm: —
- Cần từ người khác:
  - Đăng (C1-12): `POST /sessions/{id}/audio` hiện trả 501 – SV-04 hiện "đang phát triển (thẻ C1-12)" và gợi ý gõ chữ; lượt giọng chỉ chạy thật khi C1-12 xong.
  - Đăng (C1-07/C1-08): orchestrator chưa lưu `typingCps` (chỉ `pasteRatio`) – frontend đã gửi; C1-08 nhận dùng.
  - Đăng (C1-07): cần `GET /sessions/{id}` (trạng thái, câu hỏi hiện tại, tiến độ, tên nút) để SV-04 tải lại trang không mất hội thoại.
  - Đăng: `Transcript.needsConfirmation` → SV-05 xác nhận bản chép lời (GD-08); GD-07 tạm gửi thẳng bản chép lời.
  - Long (C2-02): giữ `Node.positionX/positionY` và `Edge.source` như `schemas/tree.py` hiện tại; SkillTree dựa vào các trường này.
  - Long (C2-13): bản đồ nhiệt nên trả màu theo `key` của nút (hoặc kèm `key`) để truyền thẳng vào `heat`. WebSocket gửi `{channel, event, payload}` và nhận thêm `action: "unsubscribe"`.
  - Mọi người viết backend: lỗi luôn qua `AppError` với `code` ổn định. Frontend hiện câu theo `code`, không hiện `message` của máy chủ.
  - Long (C2-07), các giả định GD-04 đang dựa vào:
    - sai email hoặc mật khẩu trả **401**; khóa tạm trả **423**;
    - `PATCH /me` cần body (vd. `{fullName, avatarUrl}`), OpenAPI hiện chưa có nên ME-01 chưa sửa được hồ sơ;
    - tự gọi `/auth/refresh` khi token 30 phút hết hạn chưa làm, sẽ làm khi C2-07 chốt cách gửi refresh token;
    - `forgot-password` hiện nhận `email` ở **query**; nếu chuyển sang body thì báo Thắng.
    - Lỗi `EmailStr` chặn đuôi `.test` (Quyền đã báo) làm tài khoản demo `@whybi.test` đăng nhập bị 422.
  - Long (C2-08), các giả định GD-04 đang dựa vào:
    - `POST /classes/join` sai mã trả 404, đã ở trong lớp trả 409, sai định dạng trả 422;
    - trả `ClassOut` có `id` để chuyển sang SV-02;
    - `GET /classes` cho SV trả các lớp đã tham gia.
    - Figma SV-01 có tiến độ "4/7 nút", nhưng `ClassOut` chưa có trường này; GD-06 sẽ lấy từ `my-map` (C2-10).

## GD-05 – GV-01, GV-02, GV-03 (2026-10-24)

- Xong: GV-01 danh sách lớp (số liệu tổng hợp tính từ `GET /classes`, nút theo trạng thái cây), GV-02 tổng quan lớp (lớp + phiên bản cây), GV-03 tải giáo trình
  (kiểm PDF/DOCX ≤ 20 MB ở trình duyệt, tiến độ nghe kênh `job:{jobId}` sự kiện `job.progress`). Test: `src/test/gd05.test.tsx`.
- Cần từ người khác:
  - Long (C2-08): `GET /classes/{id}` để GV-02/03 khỏi tìm lớp trong danh sách; `POST /classes/{id}/syllabi` khai báo thân 202 `JobAccepted` trong OpenAPI (hiện kiểu trả về là `void`, màn đang ép kiểu).
  - Long: danh sách môn cho GV (`GET /admin/courses` chỉ QTV) thì mới làm được nút "Tạo lớp học phần" ở GV-01; chưa làm nút này.
  - Chưa có API đọc trạng thái giáo trình đã tải: tải lại trang giữa chừng thì GV-03 không khôi phục được thanh tiến độ.
  - Phần Figma chưa làm: hoạt động gần đây, cảnh báo điểm nghẽn gốc (cần C2-13), thống kê ghép cặp ở GV-02.

## GD-09 – GV-04 Trình sửa cây và rubric (2026-10-24)

- Xong: tải bản nháp (`GET /classes/{id}/tree?draft=true`), thêm nút, nối cạnh bằng kéo thả (409 `CYCLE_DETECTED` hiện đường đi theo tên nút), xóa cạnh tiên quyết,
  sửa tên / chương / Bloom, sửa rubric (ý chính, quan niệm sai, ngưỡng), lưu nháp, duyệt, sinh lại bằng AI, phát hành (liệt kê `details.errors` khi 422), tạo bản nháp từ bản đã phát hành.
  Cảnh báo "N nút chưa duyệt rubric" theo BR-05. Test: `src/test/gd09.test.tsx`.
- Cần từ Long (C2-09):
  - `DELETE /nodes/{id}` và API gộp nút: nút "Xóa nút", "Gộp nút" đang khóa, chưa làm giả.
  - OpenAPI `POST /classes/{id}/tree-versions` nên khai báo body tùy chọn; `details.errors` của `PUBLISH_CHECK_FAILED` nên là mảng chuỗi tiếng Việt.
- Chưa làm (thuộc GD-14): lịch sử, so sánh, khôi phục phiên bản. "Kiểm tra DAG" riêng chưa có vì backend chặn chu trình ngay khi nối và kiểm lại khi phát hành.
