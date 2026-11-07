# docs/status/long.md   (chỉ Long sửa)

> Cập nhật sau mỗi thẻ (kế hoạch §4.2). Mọi người – và mọi phiên AI – đọc hết `docs/status/` trước khi sửa code.

- Xong:
  - C2-08: lớp học phần, mã tham gia 8 ký tự, SV tham gia lớp (gọi `MasteryService.ensure_student`), tải giáo trình
    PDF/DOCX ≤ 20 MB lên kho S3 (tự tạo bucket `S3_BUCKET`), tạo `syllabus_documents` + job Celery, trả `jobId`. Không có migration.
  - C2-16: phiên bản cây (FR-SK-10). `GET /classes/{id}/tree-versions` (mới nhất trước), `POST /tree-versions/{v}/restore`
    (sao thành DRAFT mới, bản cũ giữ nguyên, rubric duyệt lại), `GET /tree-versions/{a}/compare/{b}` → `TreeDiff`
    (nút thêm / bỏ / đổi theo key, cạnh thêm / bỏ). Endpoint compare là bổ sung ngoài Bảng 5.10 – Thắng (GD-14) dùng cho màn so sánh.
  - C2-15 (phần 2/2): ưu tiên nút nghẽn, GV điều chỉnh cặp, thống kê hiệu quả. Chi tiết `docs/spec/mx4-matching.md`.
    - `POST matching-rounds {priorityNodeId}` hết 501: nút được cộng thêm vào p(n); nút lạ ⇒ 404 `NODE_NOT_IN_TREE`.
    - `PATCH /matches/{id}` hết 501: `{cancel:true}` hoặc `{replaceStudentId, withStudentId}` (lỗi: 409 `MATCH_INVALID_STATE` · 422 `REPLACE_NOT_IN_MATCH` ·
      404 `STUDENT_NOT_IN_CLASS` · 409 `STUDENT_NOT_OPTED_IN` · 409 `STUDENT_BUSY` · 422 `NO_COMPLEMENTARY_NODES`).
    - `GET /classes/{id}/matching-stats` → `MatchingStats {totalMatches, accepted, declined, expired, studied, itemsTotal, itemsVerified, acceptRate, studiedRate, verifiedRate}` (chỉ GV chủ lớp).
    - Không đổi schema CSDL. Thắng (GD-12): chạy `npm run gen:api`; màn GV-09 thêm chọn nút ưu tiên, nút hủy / thay SV, khối thống kê.
    - Quyền (KT-14): đã thêm route mới vào bảng `PHAN_QUYEN`.
  - C2-20: lịch sử phiên và báo cáo lớp (FR-TB-15, FR-HM-10). Không đổi CSDL, không thêm thư viện (PDF dựng bằng PyMuPDF có sẵn).
    - SV: `GET /me/sessions?class_id=` (kết quả các phiên đã chấm, mới nhất trước), `GET /me/sessions/{id}` → `ProfileSession`
      (kết quả + transcript từng lượt + `audioUrl` nghe lại qua `GET /turns/{id}/audio`; chỉ phiên của mình, ghi âm quá hạn thì không có `audioUrl`).
    - GV: `GET /classes/{id}/report?format=csv|pdf` tải tệp. CSV (UTF-8 có BOM): lưới SV × nút (nhãn "Đạt", "Chưa đạt"…) + 3 dòng tổng
      theo nút (Đã thử, Đạt, Tỉ lệ Đạt %), ô tên / MSSV bắt đầu bằng `= + - @` được thêm `'` (chống CSV injection). PDF: tổng quan, bảng nút
      (màu có chữ), cảnh báo điểm nghẽn, tiến độ từng SV. Số liệu lấy từ `HeatmapService.snapshot` nên khớp màn bản đồ nhiệt.
  - C2-19: thông báo (FR-AD-08, Bảng 5.11). Không đổi CSDL. `NotificationService.notify(...)` ghi `notifications` và chỉ GIAO (đẩy `notification`
    lên kênh `user:{id}` + email qua Celery `app.workers.notifications.deliver_email`, hàng đợi `aggregation`) SAU khi giao dịch của bên gọi commit;
    rollback thì bỏ. Chưa cấu hình `SMTP_HOST` thì email chỉ ghi log. `GET /notifications?unread_only=&limit=`, `POST /notifications/{id}/read`,
    `POST /notifications/read-all`. Payload WebSocket cùng dạng `NotificationOut` (`id, type, title, content, link, isRead, createdAt`).
    Đã nối: gợi ý ghép cặp mới (`MATCH_PROPOSED`, cả ghép lô lẫn ghép theo sự kiện của C2-15) và cả hai chấp nhận (`MATCH_ACCEPTED`, kèm email liên hệ).
    Thắng: `link` là đường dẫn trong ứng dụng (`/sv/classes/{id}/peers`).
  - Sửa theo rà soát bảo mật C2-18: khóa tài khoản / QTV đặt lại mật khẩu thu hồi ngay mọi access token cũ (`Revocations.revoke_user`, kiểm ở
    `user_from_token` theo claim `t0` = giờ cấp có phần thập phân, nên không hở trong cùng một giây; thu hồi trước khi commit); ghi âm tính hạn mức TRƯỚC khi gọi STT, dưới khóa theo lớp / SV (`QuotaService.reserve_audio`), ước lượng thời
    lượng tệp nén lấy bitrate sàn nên tính dư thay vì hụt.
  - C2-18: quản trị (FR-AD-03, 04, 06, 07). Migration `412b81e85505`: bảng `usage_quotas`, `usage_records` (33 bảng).
    - Tài khoản: `GET|POST /admin/users`, `PATCH /admin/users/{id}` (khóa / mở khóa, đổi tên), `POST /admin/users/{id}/reset-password`,
      `POST /admin/users/import` (CSV UTF-8: `mssv, ho_ten, email, [khoa]`; trả `created` / `skipped` / `errors` theo dòng).
      Mật khẩu ban đầu ngẫu nhiên 10 ký tự, **chỉ trả một lần**, không vào nhật ký. Môn học: `GET|POST /admin/courses`, `PUT /admin/courses/{id}`.
    - Hạn mức: `GET|PUT /admin/quotas` (theo lớp `CLASS` hoặc SV `STUDENT`; `null` = không giới hạn, cả hai `null` = bỏ). Vượt hạn mức ⇒ **429
      `QUOTA_EXCEEDED`** (`details.kind` = `TOKENS` | `AUDIO_MINUTES`) khi bắt đầu phiên, gửi lượt / hết giờ, tải ghi âm.
      **Đăng chú ý** – đã sửa nhẹ `session_orchestrator.py` và `api/sessions.py`: `_active`/`start_session`/`audio_node` gọi `QuotaService.check`;
      `handle_turn`/`handle_timeout` bọc thêm `_record_tokens` (ghi `gateway.tokens_used` vào `usage_records`); upload ghi âm gọi `orch.record_audio`.
      Thời lượng ghi âm: WAV đọc đúng, webm/ogg/mp3/m4a **ước lượng theo dung lượng** (STT chưa trả thời lượng).
    - Cờ vi phạm: `GET /admin/flags` (QTV thấy mọi lớp, GV chỉ lớp mình), `POST /admin/flags/{id}/resolve`; nhật ký thao tác: `GET /admin/audit-logs` (QTV).
      Xử lý cờ chỉ đánh dấu đã xử lý – chưa đổi kết quả phiên (BR-12 "GV cho phép tính kết quả" chưa làm).
  - C2-17: cấu hình lớp, hồ sơ SV, ghi âm (FR-HM-07, 08, 09; NFR-09). Migration `a3f1c9d2e7b4` thêm `class_sections.challenge_count` (nối sau migration của #124).
    - `GET|PUT /classes/{id}/settings` → `ClassSettings` (đã chuyển sang `schemas/heatmap.py`): đổi ngưỡng xanh / vàng, cỡ mẫu thì
      `HeatmapService.update_settings` tính lại màu cả lớp, ghi `class_node_stats` và đẩy `heatmap.node` / `heatmap.alert`.
      **Ngưỡng Đạt và số câu phản biện hiện chỉ được lưu** – Orchestrator (Đăng) chưa đọc: nhờ Đăng nối `ClassService.get_settings`
      vào Judge (`pass_threshold`) và `max_questions` (3–5) khi làm C1-15.
    - `GET /classes/{id}/students/{s}/profile` → `StudentProfile` (tiến độ từng nút + mọi phiên kèm transcript, kết quả chấm, ghi âm).
      Mới: `services/session_history.py` (chỉ ĐỌC bảng phiên của Orchestrator; C2-20 dùng lại).
    - `GET /turns/{id}/audio`: nghe lại ghi âm – SV chủ phiên hoặc GV phụ trách lớp; hết hạn / không lưu ⇒ 404 `AUDIO_NOT_AVAILABLE`.
    - `GET /classes/{id}/heatmap?q=&anonymize=` và `.../nodes/{n}/detail?anonymize=`: lọc theo tên / MSSV, chế độ trình chiếu ("SV 01"…).
    - **Cần Đăng:** `audioRef` trong `POST /turns` do client gửi và Orchestrator lưu nguyên vào `session_turns.audio_url`. Phía đọc / dọn
      (`session_history.audio_key`) đã chỉ nhận đúng `s3://audio/<session_id>/<uuid>.<đuôi>`; nên kiểm cùng luật ngay khi nhận lượt
      (`handle_turn`) để không lưu tham chiếu lạ.
    - Beat `purge-audio` (03:00 hằng ngày): xóa đối tượng ghi âm quá `AUDIO_RETENTION_DAYS` ngày, đặt `audio_url = NULL`, giữ transcript.
  - C2-15 (phần 1/2, PR này): **ghép cặp theo sự kiện** trong hạn kiểm tra bài cũ của nút (FR-PM-04), thay hướng "cổng tỉ lệ Đạt".
    Phần 2 (ghép tay, đổi người dạy, hủy, thống kê) làm ở PR sau. Chi tiết luồng: `docs/spec/mx4-matching.md`.
    - Luồng: SV Đạt nút ⇒ người dạy; không đạt ⇒ ghép ngay với người dạy còn chỗ, chưa có ⇒ hàng chờ; **một người Đạt dạy tối đa 3 người chưa Đạt**.
      Suy ra từ ma trận (không bảng hàng chờ), chạy khi có `mastery.changed` (tiến trình `mastery_listener`) và beat `live_rebalance` mỗi 60 giây.
    - API mới (chỉ GV): `PUT /classes/{id}/nodes/{nodeId}/review-window {deadlineAt}` đặt / dời hạn (404 `NODE_NOT_IN_TREE`, 422 `DEADLINE_IN_PAST`);
      `GET /classes/{id}/review-windows` ⇒ `[{nodeKey, deadlineAt, open, teacherCount, matchedCount, waitingStudentIds, message}]`.
      Cặp tạo ra có người dạy = `studentA`, người học = `studentB`, `oneWay = true`, vòng `triggerType = "LIVE"`.
    - **Migration mới `17ea8d98c97a`**: bảng thứ 31 `node_review_windows (class_id, node_key, deadline_at)`. Khóa theo key nút nên còn hiệu lực khi phát hành cây mới.
    - Beat ghép lô hằng ngày (06:00) bỏ qua lớp đang có hạn mở. Ghép lô thủ công (`POST matching-rounds`) giữ nguyên.
    - Thắng (GD-12): chạy `npm run gen:api`; thêm màn GV đặt hạn cho nút và hiện `message` / bạn còn chờ ở GV-09; cặp `LIVE` hiện qua `GET /classes/{id}/matches` như cũ.
    - Quyền (KT-14): đã thêm 2 route vào bảng `PHAN_QUYEN` (`test_bao_mat_phan_quyen.py`) và đổi kỳ vọng 30 → 31 bảng (`test_migrations.py`, `test_contracts.py`); nhờ rà lại.
    - Đăng, Thắng: thuật toán lõi của slide thêm mô hình "ghép theo sự kiện, đến trước được trước, hạn mức 3 người học" bên cạnh Blossom ghép lô.
  - C2-12: truy vết điểm nghẽn gốc (6.5.3) + cảnh báo "Nên giảng lại X". Ví dụ Hình 6.9 (Y = N6, |F| = 9,
    r(N5|N6) = 7/9) ra đúng gốc N5 Con trỏ – test hàm thuần và test CSDL thật (lớp 30 SV, cây mẫu).
  - C2-11: tổng hợp bản đồ nhiệt (hàng đợi `aggregation`) – tỉ lệ Đạt / đã thử, cỡ mẫu tối thiểu, màu Bảng 6.6,
    tách "chưa thử" / "chưa đủ mẫu" khỏi "chưa đạt". Lớp giả lập 30 SV ra đúng màu (gồm biên 70 %, 40 %, cỡ mẫu 5).
  - C2-07: đăng nhập / làm mới / đăng xuất / quên + đặt lại mật khẩu / GET + PATCH /me; Argon2id; JWT access 30 phút;
    kiểm vai trò ở mọi API (test tự quét route). Email `@whybi.test` đăng nhập được (hết lỗi 422).
  - C2-06: CSDL 30 bảng (migration `1af58d747696`) + migration `c2a06b5e9d10` thêm 13 CHECK theo từ điển dữ liệu 5.2.4.
    Chạy sạch trên CSDL mới: `upgrade head` → `alembic check` → `downgrade base` → `upgrade head`.
  - C2-05: bus sự kiện `app/realtime/bus.py` (Redis Pub/Sub + bản trong bộ nhớ cho test), schema `MasteryChanged` đã chốt.
  - C2-01 (PR riêng): test khung ứng dụng, README "Chạy bằng một lệnh", mẫu PR.
  - C2-02: schema cây đã chốt; `GET /classes/{id}/tree` trả cây mẫu 11 nút / 13 cạnh từ `seed/tree_ctdl_gt.json`.
  - C2-03: `docker compose up -d --build --wait` chạy đủ 7 dịch vụ, tất cả healthy (stt bật bằng `--profile stt`).
    - Đổi cổng host bằng biến môi trường khi máy đã bận cổng: `NGINX_PORT`, `API_PORT`, `POSTGRES_PORT`, `REDIS_PORT`, `MINIO_PORT`, `MINIO_CONSOLE_PORT`, `STT_PORT`.
    - Thứ tự khởi động: postgres, redis, minio healthy → api healthy (đã chạy `alembic upgrade head`) → nginx.
    - Sửa `STT_WHISPER_URL` thành `http://stt:8000` (cổng trong container; cổng host 9100 chỉ dùng từ ngoài).
- Phát sự kiện / hợp đồng đã chốt:
  - **Lớp học phần** (C2-08), JSON camelCase, `ClassOut { id, name, semester, joinCode, studentCount, treeStatus? }`:
    - `GET /classes` (GV, SV): GV → lớp mình phụ trách (mới tạo trước); SV → lớp đã tham gia (mới tham gia trước).
      `treeStatus`: `PUBLISHED` nếu đã phát hành, không thì trạng thái phiên bản mới nhất, chưa có cây thì `null`.
    - `POST /classes {courseId, name, semester}` (GV) → 201 `ClassOut`. Môn không có → 404 `COURSE_NOT_FOUND`.
      Mã tham gia 8 ký tự `A–Z, 2–9` (bỏ O/0, I/1), duy nhất.
    - `POST /classes/join {joinCode}` (SV) → 200 `ClassOut`. Mã nhận chữ thường, tự đổi IN HOA.
      Sai mã / lớp đã lưu trữ → 404 `JOIN_CODE_INVALID`; đã ở lớp → 409 `ALREADY_ENROLLED`; sai định dạng → 422 `VALIDATION_ERROR`.
      Lớp đã phát hành cây thì SV có ngay ô ma trận (`my-map` dùng được).
    - Tài khoản thiếu hồ sơ trong bảng `lecturers` / `students` → 403 `LECTURER_PROFILE_MISSING` / `STUDENT_PROFILE_MISSING`
      (token `dev-*` không có hồ sơ nên không tạo / tham gia lớp được – dùng tài khoản seed KT-02).
  - **Tải giáo trình** (C2-08) `POST /classes/{classId}/syllabi` (multipart, trường `file`, GV phụ trách) →
    202 `JobAccepted { jobId, documentId, channel: "job:{jobId}" }`:
    - Sai đuôi / nội dung không khớp (vd. .exe đổi đuôi .pdf – TC01) / tệp rỗng → 422 `INVALID_FILE`,
      `details.reason` ∈ `EXTENSION | CONTENT_MISMATCH | EMPTY`; quá 20 MB → 422 `FILE_TOO_LARGE` (`details.maxMb`).
    - Lớp khác → 404 `CLASS_NOT_FOUND`; không phải GV phụ trách → 403 `NOT_CLASS_OWNER`.
      Kho S3 lỗi → 503 `STORAGE_UNAVAILABLE`; hàng đợi lỗi → 503 `JOB_QUEUE_UNAVAILABLE` (tài liệu chuyển `FAILED`).
    - Tệp lưu ở `s3://{S3_BUCKET}/syllabi/{classId}/{documentId}.{pdf|docx}` (`syllabus_documents.file_url`);
      đọc lại bằng `app.services.storage.default_storage().get(url)`.
    - Job: `celery.send_task("app.workers.documents.process_syllabus", args=[documentId, jobId], task_id=jobId)` → hàng đợi `documents`.
  - **Điểm nghẽn gốc** (C2-12):
    - `app/algorithms/rootcause.py`: `analyze(g, y, F, not_mastered, θ=0,6, D=3, min_sample)` → `RootCause | None`
      (None khi |F| < cỡ mẫu); score = r × (1 + 0,1 × khoảng cách), hòa điểm chọn nút xa hơn rồi theo key; không ứng viên ⇒ Y tự là gốc.
    - `HeatmapService.trace_root_causes(class_id)` → `list[HeatmapAlert]`; ghi `class_node_stats.root_cause_node_id / root_cause_score`
      cho mọi nút (hết đỏ ⇒ NULL). Hàng đợi `aggregation` và phát hành cây gọi sau mỗi lần tính lại, cùng giao dịch.
    - `HeatmapAlert` (payload `heatmap.alert`) thêm trường tùy chọn: `nodeKey`, `rootCauseNodeKey`, `rootCauseTitle`, `isSelf`,
      `score`, `conditionalFailRate`, `failedCount`, `distance`. `message` dạng "Nên giảng lại N5 Con trỏ".
    - "Chưa Đạt X" = không MASTERED / NEEDS_REVERIFY (cùng định nghĩa bản đồ nhiệt); SV chưa có ô ⇒ chưa Đạt.
    - `MasteryService.class_matrix(class_id)` (chỉ đọc): cây đang phát hành + ô theo key × SV.
  - **Bản đồ nhiệt** (C2-11):
    - Màu (`app/algorithms/heatmap.py`): đã thử < `min_sample` (5) ⇒ GREY; p ≥ 0,7 ⇒ GREEN; p ≥ 0,4 ⇒ YELLOW; còn lại RED.
      p = Đạt / đã thử (so bằng phân số, 21/30 là GREEN). Đạt = MASTERED hoặc NEEDS_REVERIFY; IN_PROGRESS xét theo `prev_state`.
      Ngưỡng đọc từ `class_sections.color_thresholds {green, yellow}` và `min_sample` (C2-17 sẽ có màn cấu hình).
    - `HeatmapNode` (payload `heatmap.node`) thêm trường tùy chọn: `nodeKey`, `sample` (`HeatSample`: NO_ATTEMPT / INSUFFICIENT /
      SUFFICIENT), `label` (chữ đi kèm màu, vd. "✗ Điểm nghẽn – 2/9 Đạt", "Chưa đủ mẫu (4/5 SV đã thử)"), `enrolledCount`,
      `attemptedCount`, `passedCount`, `minSample`.
    - Luồng: `mastery.changed` → `heatmap.register_handlers` (trong tiến trình `events`) → task `aggregation.recompute_node`
      → upsert `class_node_stats`. Bỏ qua lý do SESSION_STARTED / SESSION_ABANDONED / UNLOCKED (không đổi số liệu).
    - Beat `heatmap-reconcile` (10 phút) → `reconcile_all` → `recompute_class` mỗi lớp đã phát hành: bù sự kiện Pub/Sub bị mất.
    - `MasteryService.columns(class_id, node_ids?)`: đọc cột ma trận (chỉ SV đang ghi danh, chỉ nút bản đang phát hành).
  - **Xác thực** (C2-07), JSON camelCase:
    - `POST /auth/login {email, password}` → `{accessToken, refreshToken, tokenType:"bearer", expiresIn:1800}`.
      Sai email hoặc mật khẩu → 401 `INVALID_CREDENTIALS` (cùng một lỗi); tài khoản khóa → 403 `ACCOUNT_DISABLED`.
    - `POST /auth/refresh {refreshToken}` → cặp token mới; refresh cũ bị thu hồi (dùng lại → 401 `TOKEN_REVOKED`).
    - `POST /auth/logout {refreshToken?}` (kèm Bearer) → 204; access (và refresh) bị thu hồi qua Redis.
    - `POST /auth/forgot-password {email}` → luôn 202. `POST /auth/reset-password {token, newPassword}` → 204, token dùng một lần.
      Chưa có SMTP: ở dev token đặt lại được in ra log api.
    - `GET /me` → `{id, fullName, email, role, avatarUrl}`. `PATCH /me {fullName?, avatarUrl?, currentPassword?, newPassword?}`;
      đổi mật khẩu bắt buộc `currentPassword` (400 `CURRENT_PASSWORD_REQUIRED` / `WRONG_PASSWORD`). Mật khẩu mới 8–128 ký tự.
    - Lỗi token: 401 `UNAUTHORIZED` (thiếu), `TOKEN_EXPIRED` (quá 30 phút), `INVALID_TOKEN`, `TOKEN_REVOKED`. Sai vai trò → 403 `FORBIDDEN`.
    - Claims access: `sub` (id người dùng), `role`, `name`, `typ="access"`, `jti`, `iat`, `exp`. Backend: `user: CurrentUser = Lecturer | Student | Admin | AnyUser…`.
    - Ngoài dev / test bắt buộc `JWT_SECRET` riêng ≥ 32 ký tự (không thì api báo lỗi khi tạo token).
  - **CSDL** (C2-06): 30 bảng ở `app/models/{users,tree,session,peer}.py`, head `c2a06b5e9d10`.
    - CHECK mới: `mastery_records` (`state` ∈ MasteryState, `attempts ≥ 0`, `best_score` 0–100), `evaluations`
      (`total_score` 0–100, `verdict` ∈ PASSED/FAILED), `session_turns` (`turn_no ≥ 1`, `stt_confidence`, `paste_ratio` 0–1),
      `class_node_stats` (`pass_rate` 0–1, `passed ≤ attempted`), `prerequisite_edges` (`confidence` 0–1, không tự trỏ),
      `rubrics.pass_threshold` 0–100, `peer_matches` (A ≠ B).
    - Thêm giá trị vào `MasteryState` / `Verdict` ⇒ cần migration mới (báo Long).
    - Test CSDL thật: đặt `TEST_DATABASE_URL` (CI job backend đã đặt).
  - **Bus sự kiện** (C2-05) `from app.realtime.bus import get_bus`:
    - `get_bus().publish(topic, model)` / `get_bus().subscribe(topic, handler)`; handler nhận **model Pydantic** đã kiểm.
    - `session.completed` → `SessionResult` (Đăng phát). `mastery.changed` → `MasteryChanged` (chỉ MasteryService phát).
    - Trên dây: kênh Redis trùng tên chủ đề, JSON camelCase. Sai kiểu payload → `TypeError`; chủ đề lạ → `UnknownTopic`.
    - Redis: handler chỉ chạy trong tiến trình gọi `bus.start()` (luồng nền) hoặc `bus.listen()`. Pub/Sub không lưu tin.
    - `APP_ENV=test` hoặc `EVENT_BUS=memory` → `InMemoryEventBus` (đồng bộ, không cần Redis).
  - **`MasteryChanged`** (`schemas/mastery.py`): `classId, studentId, nodeId, nodeKey?, oldState?, newState, unlockedNodeIds[], sessionId?, occurredAt`.
  - **`backend/app/models/schemas/tree.py`** (C2-02) gồm `TreeVersion { id, classId, versionNo, status, changeNote, publishedAt, nodes[], edges[] }`:
    - `Node { id, key, code, title, description, chapterRef, bloomLevel, positionX, positionY, rubric? }`;
    - `Edge { id, fromKey, toKey, source, confidence }`: cạnh nối theo **key** nút, không theo id;
    - `Rubric { keyPoints[], optionalPoints[], misconceptions[], scenarios[], targetBloom, passThreshold, minChallenges, minPassedChallenges, sourcePages[], approved }`;
    - JSON luôn camelCase;
    - `TreeVersion` tự từ chối khi key nút trùng, cạnh trỏ tới key không có, hoặc cạnh tự trỏ;
    - mới thêm `ChallengeScenarioSchema.expectedPoints` (tùy chọn).
  - **`GET /api/v1/classes/{classId}/tree`** (vai GV, SV):
    - Lớp mẫu có id cố định `0fcd3055-a08a-5a08-b881-bbab21c660c2` (`app.services.skill_tree.SEED_CLASS_ID`). Ví dụ: `curl -H "Authorization: Bearer dev-lecturer" http://localhost:8000/api/v1/classes/0fcd3055-a08a-5a08-b881-bbab21c660c2/tree`.
    - id nút và cạnh là uuid5, ổn định giữa các lần gọi và giữa các máy.
    - Lớp khác trả 404 `CLASS_NOT_FOUND`. Không có token trả 401. QTV trả 403.
  - **Token dev** `Bearer dev-lecturer` / `dev-student` / `dev-admin`: vẫn giữ sau C2-07 vì CSDL chưa có tài khoản mẫu.
    - Chỉ có hiệu lực khi `ALLOW_DEV_TOKENS=true` (có sẵn trong `.env.example`), `APP_ENV=dev|test` và `DEMO_MODE=0`.
    - Xóa khi seed tài khoản (KT-02, `scripts/seed_db.py`) đã merge; khi đó đăng nhập thật bằng `gv@whybi.test` / `Whybi@2026`.
  - `app/algorithms/dag.py`: thêm `build_graph(tree)` và `find_cycle(g) -> list[key] | None`.
  - Hướng đi lên CSDL:
    - C2-06 tạo bảng; `scripts/seed_db.py` nạp seed vào CSDL với cùng các uuid5.
    - C2-09 thay phần đọc JSON trong `SkillTreeService.get_class_tree` bằng truy vấn phiên bản đã phát hành hoặc bản nháp.
    - Chữ ký API và schema giữ nguyên.
- Đang làm: —
- Cần từ người khác:
  - Thắng (GD-10): tô SkillTree `heat` theo `nodeKey` của `HeatmapNode`; hiện `label` cạnh màu (GREY có hai nghĩa: chưa thử / chưa đủ mẫu).
  - Thắng (GD-10): chạy `npm run gen:api` (HeatmapAlert có trường mới); nút có `rootCauseNodeKey` hiện ◎ GỐC kèm chữ `message` ("Nên giảng lại …").
  - Quyền (KT-11): TC12 truy vết gốc – xem `backend/tests/unit/test_rootcause_db.py` (dựng ví dụ Hình 6.9 trên cây mẫu).
  - Đăng (C1-10): `TreeVersion` giờ từ chối cạnh trỏ tới key không có và cạnh tự trỏ. Nếu sinh cây nháp bằng `call_json`,
    dùng schema nháp riêng (không validator) hoặc lọc cạnh lỗi trước, rồi mới dựng `TreeVersion` và gọi `sanitize` (C2-09).
  - Thắng: chạy `npm run gen:api` để lấy kiểu `TreeVersion` (có thêm `expectedPoints`). Gọi API bằng token `dev-lecturer`.
  - Quyền: `scripts/seed_db.py` (KT-02) đọc cây theo đúng schema này. Nếu cần id ổn định, dùng `SEED_CLASS_ID` và các uuid5 trong `app/services/skill_tree.py`.
  - Quyền (KT-02): `seed_db.py` băm mật khẩu bằng `app.core.security.hash_password` (Argon2id) khi nạp `users`.
    Đã bỏ xfail ở `tests/integration/test_smoke_api.py::test_dang_nhap_tai_khoan_demo_khong_bi_422`.
  - Thắng: màn AUTH dùng `/auth/login`, lưu `refreshToken`, gọi `/auth/refresh` khi gặp 401 `TOKEN_EXPIRED`.
  - Long (C2-04) / người deploy: đặt `JWT_SECRET` dài ngẫu nhiên trên VM demo.
  - Cả đội: gửi username GitHub để bật `.github/CODEOWNERS`.
  - Người điều phối: bật bảo vệ nhánh `main`.
  - Đăng (C1-07): cuối phiên, sau khi lưu kết quả phiên, gọi `get_bus().publish(TOPIC_SESSION_COMPLETED, session_result)`.
  - Đăng (C1-09): `process_syllabus(documentId, jobId)` đọc tệp bằng `default_storage().get(doc.file_url)`
    (`MinioStorage` tự tạo bucket khi ghi), chuyển `syllabus_documents.status` UPLOADED → PARSING → PARSED / FAILED,
    phát tiến độ lên kênh `job:{jobId}`.
  - Thắng (GD-04 / GD-05): thêm câu cho mã mới `JOIN_CODE_INVALID`, `ALREADY_ENROLLED`, `FILE_TOO_LARGE`,
    `COURSE_NOT_FOUND`, `STUDENT_PROFILE_MISSING`, `JOB_QUEUE_UNAVAILABLE`, `STORAGE_UNAVAILABLE` vào `FRIENDLY`; chạy `npm run gen:api`
    (`JobAccepted` có thêm `channel`; `JoinRequest.joinCode` nhận chữ thường).
