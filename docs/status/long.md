# docs/status/long.md   (chỉ Long sửa)

> Cập nhật sau mỗi thẻ (kế hoạch §4.2). Mọi người – và mọi phiên AI – đọc hết `docs/status/` trước khi sửa code.

- Xong:
  - C2-08: lớp học phần, mã tham gia 8 ký tự, SV tham gia lớp (gọi `MasteryService.ensure_student`), tải giáo trình
    PDF/DOCX ≤ 20 MB lên kho S3 (tự tạo bucket `S3_BUCKET`), tạo `syllabus_documents` + job Celery, trả `jobId`. Không có migration.
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
