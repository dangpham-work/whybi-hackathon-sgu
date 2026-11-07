# docs/status/long.md   (chỉ Long sửa)

> Cập nhật sau mỗi thẻ (kế hoạch §4.2). Mọi người – và mọi phiên AI – đọc hết `docs/status/` trước khi sửa code.

- Xong:
  - C2-06: CSDL 30 bảng (migration `1af58d747696`) + migration `c2a06b5e9d10` thêm 13 CHECK theo từ điển dữ liệu 5.2.4.
    Chạy sạch trên CSDL mới: `upgrade head` → `alembic check` → `downgrade base` → `upgrade head`.
  - C2-01 (PR riêng): test khung ứng dụng, README "Chạy bằng một lệnh", mẫu PR.
  - C2-02: schema cây đã chốt; `GET /classes/{id}/tree` trả cây mẫu 11 nút / 13 cạnh từ `seed/tree_ctdl_gt.json`.
  - C2-03: `docker compose up -d --build --wait` chạy đủ 7 dịch vụ, tất cả healthy (stt bật bằng `--profile stt`).
    - Đổi cổng host bằng biến môi trường khi máy đã bận cổng: `NGINX_PORT`, `API_PORT`, `POSTGRES_PORT`, `REDIS_PORT`, `MINIO_PORT`, `MINIO_CONSOLE_PORT`, `STT_PORT`.
    - Thứ tự khởi động: postgres, redis, minio healthy → api healthy (đã chạy `alembic upgrade head`) → nginx.
    - Sửa `STT_WHISPER_URL` thành `http://stt:8000` (cổng trong container; cổng host 9100 chỉ dùng từ ngoài).
- Phát sự kiện / hợp đồng đã chốt:
  - **CSDL** (C2-06): 30 bảng ở `app/models/{users,tree,session,peer}.py`, head `c2a06b5e9d10`.
    - CHECK mới: `mastery_records` (`state` ∈ MasteryState, `attempts ≥ 0`, `best_score` 0–100), `evaluations`
      (`total_score` 0–100, `verdict` ∈ PASSED/FAILED), `session_turns` (`turn_no ≥ 1`, `stt_confidence`, `paste_ratio` 0–1),
      `class_node_stats` (`pass_rate` 0–1, `passed ≤ attempted`), `prerequisite_edges` (`confidence` 0–1, không tự trỏ),
      `rubrics.pass_threshold` 0–100, `peer_matches` (A ≠ B).
    - Thêm giá trị vào `MasteryState` / `Verdict` ⇒ cần migration mới (báo Long).
    - Test CSDL thật: đặt `TEST_DATABASE_URL` (CI job backend đã đặt).
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
  - **Token tạm khi chưa có C2-07**: `Authorization: Bearer dev-lecturer` / `dev-student` / `dev-admin`.
    - Chỉ có hiệu lực khi `ALLOW_DEV_TOKENS=true` (có sẵn trong `.env.example`), `APP_ENV=dev|test` và `DEMO_MODE=0`. Mặc định tắt. C2-07 sẽ xóa.
  - `app/algorithms/dag.py`: thêm `build_graph(tree)` và `find_cycle(g) -> list[key] | None`.
  - Hướng đi lên CSDL:
    - C2-06 tạo bảng; `scripts/seed_db.py` nạp seed vào CSDL với cùng các uuid5.
    - C2-09 thay phần đọc JSON trong `SkillTreeService.get_class_tree` bằng truy vấn phiên bản đã phát hành hoặc bản nháp.
    - Chữ ký API và schema giữ nguyên.
- Đang làm: — (C2-05 ở PR #86)
- Cần từ người khác:
  - Đăng (C1-10): `TreeVersion` giờ từ chối cạnh trỏ tới key không có và cạnh tự trỏ. Nếu sinh cây nháp bằng `call_json`,
    dùng schema nháp riêng (không validator) hoặc lọc cạnh lỗi trước, rồi mới dựng `TreeVersion` và gọi `sanitize` (C2-09).
  - Thắng: chạy `npm run gen:api` để lấy kiểu `TreeVersion` (có thêm `expectedPoints`). Gọi API bằng token `dev-lecturer`.
  - Quyền: `scripts/seed_db.py` (KT-02) đọc cây theo đúng schema này. Nếu cần id ổn định, dùng `SEED_CLASS_ID` và các uuid5 trong `app/services/skill_tree.py`.
  - Cả đội: gửi username GitHub để bật `.github/CODEOWNERS`.
  - Người điều phối: bật bảo vệ nhánh `main`.
  - Đăng (C1-09) và Long (C2-08): bucket `S3_BUCKET` chưa được tạo sẵn; code tải tệp cần tạo bucket nếu chưa có (`make_bucket`).
