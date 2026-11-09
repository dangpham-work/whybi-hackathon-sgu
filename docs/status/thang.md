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
  - `DELETE /nodes/{id}` đã có; bỏ chức năng gộp nút (gộp = xóa một nút rồi sửa nút còn lại).
  - OpenAPI `POST /classes/{id}/tree-versions` nên khai báo body tùy chọn; `details.errors` của `PUBLISH_CHECK_FAILED` nên là mảng chuỗi tiếng Việt.
- Chưa làm (thuộc GD-14): lịch sử, so sánh, khôi phục phiên bản. "Kiểm tra DAG" riêng chưa có vì backend chặn chu trình ngay khi nối và kiểm lại khi phát hành.

## GD-10 – GV-05, GV-06 (2026-10-24)

- Xong: GV-05 bản đồ nhiệt (chế độ cây tô màu theo `HeatmapSnapshot.nodes`, chế độ lưới SV × Nút có tên + MSSV, panel cảnh báo điểm nghẽn, sĩ số / trực tuyến / phiên đang diễn ra);
  cập nhật trực tiếp qua `class:{id}:heatmap` (`heatmap.cell|node|alert`, `lib/heatmap.ts`), nối lại thì tải lại ảnh chụp. GV-06 chi tiết nút: SV theo trạng thái, quan niệm sai, truy vết nút gốc.
  Test: `src/test/gd10.test.tsx`. Bấm nút trên cây → GV-06 (không dùng modal).
- Sinh lại `src/lib/api-types.ts` từ OpenAPI hiện tại của backend (bản cũ thiếu các trường C2-13); không có lỗi kiểu ở màn cũ.
- Cần từ Long (C2-13): `NodeDetail.topMisconceptions` là `list[dict]` – màn đang đọc `content` / `count`; xin chốt tên trường. Payload `heatmap.cell|node` không có trong OpenAPI nên frontend tự khai báo kiểu (khớp `schemas/mastery.py`).
- Chưa làm: tab "Điểm nghẽn", "Ghép cặp", danh sách "Đang diễn ra", nút "Nhắc SV thử lại", "Xuất danh sách" (cần API); ẩn tên khi chiếu, lọc, xuất báo cáo thuộc GD-14 / GD-16.

## GD-13 – GV-07, GV-08 (2026-10-24)

- Xong: GV-09 chạy vòng ghép cặp (có chọn nút ưu tiên), danh sách cặp (A/B, nút dạy–học, trọng số, trạng thái), thống kê `matching-stats`;
  SV-07 liệt kê gợi ý với tên nút từ `my-map`, hạn còn lại (BR-09), chấp nhận / từ chối / "Đã học cùng", nút "Giảng lại … để xác nhận" mở phiên có `peerMatchItemId`.
  Test: `src/test/gd11.test.tsx`. Sinh lại `api-types.ts` từ OpenAPI hiện tại (trùng bản ở PR GD-10).
- Cần từ Long (C2-14):
  - Công tắc "Tham gia ghép cặp" (FR-PM-01) đang khóa: `PUT /enrollments/{id}/peer-opt-in` cần `enrollmentId` nhưng không API nào trả cho SV (ClassOut, my-map đều thiếu), cũng chưa có API đọc trạng thái bật/tắt hiện tại. Xin thêm `enrollmentId` + `peerOptIn` vào `ClassOut` (hoặc `GET /me/enrollments`).
  - Hàng chờ của GV-09: `waitingStudentIds` chỉ có id và chỉ trả khi chạy vòng; chưa có GET để hiện tên + lý do chờ.
- Chưa làm: bật tự chạy mỗi 24 giờ, lọc theo trạng thái, xuất danh sách (cần API); điều chỉnh cặp thủ công thuộc GD-12.

## GD-12 – SV-04 nút bật TTS và đồng hồ đếm giờ; GV-09 điều chỉnh cặp thủ công (2026-10-24)

- Xong: SV-04 có đồng hồ đếm ngược theo `Question.deadline` (hết giờ gọi `POST /sessions/{id}/timeout` đúng một lần, hiện `notice`, sang câu kế) và nút bật/tắt đọc câu hỏi
  (tải `Question.audioUrl` bằng token rồi phát; TTS lỗi thì phiên vẫn chạy). GV-09 điều chỉnh cặp thủ công: hủy cặp hoặc thay một SV (`PATCH /matches/{id}`), báo lỗi `STUDENT_BUSY`, `STUDENT_NOT_OPTED_IN`…
  Thống kê hiệu quả ghép cặp đã có từ GD-11. Test: `src/test/gd12.test.tsx`.
- Sửa lỗi gặp khi làm: `useCountdown` trả nhầm số 0 của câu cũ khi sang câu mới nên có thể gọi `/timeout` hai lần; nay giá trị gắn kèm hạn của nó.
- Xong: GV-07 hồ sơ SV (tiến độ, số phiên, điểm trung bình, cờ, trạng thái từng nút kèm tên nút từ cây, lịch sử phiên, quan niệm sai); GV-08 transcript từng lượt,
  nghe lại ghi âm (tải bằng token vì `<audio src>` không gửi được Authorization; 404 `AUDIO_NOT_AVAILABLE` báo "không còn"), 5 tiêu chí, cờ vi phạm.
  Test: `src/test/gd13.test.tsx`. Sinh lại `api-types.ts` (cùng bản với PR GD-10).
- Cần từ Long (C2-17):
  - GV-08 chỉ có `sessionId` trên đường dẫn nhưng transcript chỉ lấy được qua hồ sơ SV, nên link từ GV-07 mang theo `?classId=&studentId=`. Xin `GET /sessions/{id}/transcript` (hoặc `GET /classes/{id}/sessions/{sid}`) cho GV để mở thẳng từ nơi khác.
  - Hồ sơ SV chưa có ngày tham gia lớp, nên header chưa hiện "Tham gia dd/mm".
- Chưa làm: "Nhắc thử lại", "Xuất hồ sơ", "Gợi ý ghép cặp", "Gửi nhắc nhở" (GV-07); "Tải ghi âm", "Chấp nhận kết quả", "Gắn cờ phiên", sóng âm tổng (GV-08) – cần API tương ứng.
## GD-14 và GD-16 – GV-10, SV-08, lọc/ẩn tên/trình chiếu/xuất báo cáo GV-05, lịch sử phiên bản GV-04 (2026-10-24)

- Xong: GV-10 cấu hình ngưỡng (ngưỡng Đạt, xanh / vàng theo %, cỡ mẫu, số câu phản biện; kiểm trước khi gửi cùng luật 422 của backend);
  SV-08 lịch sử phiên (tổng hợp, lọc Đạt / Chưa đạt, mở phiên xem hội thoại và nghe lại ghi âm). Test: `src/test/gd14.test.tsx`.
  Đổi test router thành kiểm thẳng `ScreenPlaceholder` để không phụ thuộc màn nào còn thiếu.
- GV-05 tìm theo tên / MSSV (gửi `q`), "Ẩn tên khi chiếu" (gửi `anonymize=true`, tên không tới trình duyệt; tin `heatmap.cell` cũng bị làm trống tên), chế độ trình chiếu toàn màn hình, nút Xuất CSV / PDF (`GET /classes/{id}/report`, tải bằng token, lấy tên tệp từ `Content-Disposition`);
  GV-04 lịch sử phiên bản, so sánh hai bản theo tên nút, khôi phục thành bản nháp mới. Test: `src/test/gd14b.test.tsx`, `src/test/gd09.test.tsx`.
- Cần từ Long: `GET /me/sessions` không kèm tên nút nên danh sách SV-08 chưa hiện "N5 Con trỏ" (chỉ có sau khi mở phiên); xin thêm `nodeTitle` vào `SessionResult`.
## GD-15 – Màn quản trị và thông báo (2026-10-24)

- Xong: AD-01 tài khoản (tìm, lọc, tạo, khóa/mở, đặt lại mật khẩu hiện một lần, nhập CSV có báo cáo), AD-02 môn học, AD-03 cấu hình AI (model chính / dự phòng),
  AD-04 hạn mức, AD-05 cờ vi phạm + nhật ký thao tác; chuông thông báo (`NotificationBell`) trong 3 layout: danh sách, nhận mới qua kênh `user:{id}`, đánh dấu đã đọc.
  Test: `src/test/gd15.test.tsx`. Thêm `lib/criteria.ts` (trùng bản ở PR GD-13) và sinh lại `api-types.ts`.
- Cần từ Đăng / Long:
  - Đăng (C1-02): chưa có `GET /admin/ai-config` nên AD-03 bắt đầu từ giá trị mặc định thay vì cấu hình đang chạy; xin thêm GET.
  - Long (C2-18): `quotas` nhận `scopeId` (UUID) nên QTV phải dán id lớp / SV; xin API tìm lớp / SV theo tên để chọn thay vì nhập id. Không có API sửa thông tin môn ngoài PUT, chưa có xóa môn.
