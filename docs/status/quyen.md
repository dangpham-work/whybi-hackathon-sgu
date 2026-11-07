# docs/status/quyen.md   (chỉ Quyền sửa)

> Cập nhật sau mỗi thẻ (kế hoạch §4.2). Mọi người – và mọi phiên AI – đọc hết `docs/status/` trước khi sửa code.

- Xong:
  - KT-01 – mẫu bug đủ trường (mức, module, bước tái hiện, môi trường); quy trình `docs/bug-triage.md` (PR #74)
  - KT-02 – dữ liệu mẫu `seed/` + `scripts/seed_db.py` nạp bằng một lệnh (PR #77)
  - KT-03 – khung test tích hợp (`backend/tests/integration/conftest.py`, fixture `http` / `api`) và E2E Playwright; job CI `e2e` trên stack docker compose
- Phát sự kiện / hợp đồng đã chốt:
  - Test tích hợp: gắn `@pytest.mark.integration`; mặc định bỏ qua, bật bằng `RUN_INTEGRATION=1` (+ `INTEGRATION_API_URL`, mặc định http://localhost:8000)
  - E2E: `cd e2e && npm ci && npx playwright test` (`E2E_BASE_URL`, mặc định http://localhost); `npm run typecheck` không cần stack
  - CI job `e2e`: song song, lỗi làm CI thất bại (đã bỏ `continue-on-error`); báo cáo ở artifact `playwright-report`
- Đang làm: kiểm chứng lại KT-03 sau PR #92 (đã merge khi CI lỗi vì thiếu nền backend, nginx và frontend; các phần nền đã được bổ sung trên main).
- Cần từ người khác:
  - Long (C2-07): `api/auth.py` dùng `EmailStr` – email-validator chặn đuôi `.test`, `POST /auth/login` với `gv@whybi.test` trả 422 (đã kiểm trên stack local; có test xfail `test_dang_nhap_tai_khoan_demo_khong_bi_422`). Đề xuất: ngoài prod bỏ `"test"` khỏi `email_validator.SPECIAL_USE_DOMAIN_NAMES`, hoặc dùng `str` có pattern
  - Long: duyệt job `e2e` trong `.github/workflows/ci.yml`; thêm `e2e` vào required checks của main để ngăn merge khi test thất bại
  - Người có quyền admin repo: tạo bảng GitHub Projects theo mục 4 `docs/bug-triage.md`
  - GV / thư viện: giáo trình mẫu theo `seed/syllabi/README.md`

## KT-12 – bộ đo Tutee 30 phiên

- C1-06 đã merge. Chuyển runner/test và 30 kịch bản nháp từ whybi-ai@162062f; không sửa prompt, Guard hoặc API nghiệp vụ.
- Workflow riêng chạy 30 phiên fake trên GitHub, lưu artifact kt12-tutee-simulation gồm hội thoại, provenance, summary và nhãn null chờ chấm độc lập.
- Không tự điền nhãn không lộ đáp án; chưa đo chất lượng model thật, không ghi số liệu simulation thành kết quả thực nghiệm. Còn cần model thật và người chấm.
- Không test local; theo Quyền, PR thường và đóng #51 khi toàn bộ check CI pass. Không xác nhận CD/VM.
## KT-09 – MX1 và bộ đo cây

- C1-11 và GD-09 đã merge. Chuyển test/evaluator từ whybi-ai@779779f và ba tài liệu fixture tổng hợp từ seed của repo gốc, không phải giáo trình dùng nghiệm thu.
- Test pipeline trên Postgres: upload PDF/DOCX/scan, worker, DAG/rubric, duyệt/phát hành và phục hồi lỗi. Nối endpoint regenerate vào service C1-11 đã có và khôi phục node_for_edit tương ứng; không giả lập quyền sở hữu.
- Công cụ đo P/R/F1 giữ ánh xạ một-một và bằng chứng chờ GV duyệt. Chưa dùng số liệu cũ hoặc fake để báo chất lượng model thật.
- Không test local; PR thường, đóng #48 khi toàn bộ checks GitHub pass theo Quyền. Chưa xác nhận CD/VM.
## KT-04 – bộ dữ liệu và kiểm schema

- Đã chuyển từ nguồn `whybi-ai` tại `f88c288`: 58 ca Guard, 62 lời giảng nháp AI, 30 mục manifest STT và 3 cây chuẩn.
- `cd backend && uv run python ../evals/run.py check`: đọc theo schema; lỗi JSON/trường lạ/id trùng/cây có chu trình trả mã 1. Thiếu tư liệu thực tế được báo cảnh báo.
- 43 test KT-04 chạy trong pytest mặc định, không cần stack hoặc LLM; gồm CLI thành công/thất bại và dữ liệu sai.
- Giữ ba ca hồi quy luật Guard AT01/AT02/AT07; test với LLM giả luôn VALID không đại diện cho hiệu quả của toàn bộ corpus mới. KT-07 phải đo toàn bộ ca với Guard thật, không coi test đơn vị xanh là đạt mục tiêu 90%.
- Cần: người gán nhãn độc lập cho 62 lời giảng; 30 file ghi âm có đồng ý sử dụng; GV xác nhận cây chuẩn và giáo trình đi kèm.
- Chờ CI của PR KT-04 và Long duyệt; Đăng rà thay đổi giới hạn test Guard về các ca hồi quy ban đầu. Không đổi code Guard hoặc kết quả đánh giá thực nghiệm.
## KT-10 – giọng nói và bộ đo STT

- C1-12 và GD-08 đã merge. Chuyển test/metrics/runner từ whybi-ai@3586904.
- CI backend kiểm audio→transcript→lượt VOICE trên Postgres; Playwright kiểm ghi/dừng/ghi lại/gửi, lỗi STT, xác nhận khi confidence=0,65 và giới hạn 3 phút với microphone giả và HTTP có kịch bản.
- Bộ đo giữ WER, thuật ngữ, độ trễ và provenance; chưa có 30 bản ghi người thật được đồng ý và xác nhận độc lập. Không dùng fixture hoặc provider fake làm số liệu chất lượng.
- Không test local; PR thường, đóng #49 khi toàn bộ checks GitHub pass theo Quyền. Chưa xác nhận CD/VM.
## KT-05 – giả lập qua API phiên thật

- Tiên quyết C1-01, C2-05 và API C1-07 (PR #119) đã merge. Script chuyển từ whybi-ai bcf5f1d.
- Khôi phục phần seed DB của KT-02 còn là stub trên main: scripts/seed_db.py nạp 32 tài khoản, lớp và cây trong CSDL demo; băm mật khẩu và chạy lại không xóa dữ liệu.
- Script simulate_students.py đăng nhập riêng từng SV, gửi phiên/lượt/result, đợi my-map xác nhận MasteryService; N5 mặc định 9 MASTERED / 21 NOT_PASSED. Chạy lại không tạo phiên khi dữ liệu đã đúng, dừng khi xung đột.
- Demo riêng: APP_ENV=dev, LLM_MODE=fake, DEMO_MODE=1; sau migration chạy seed_db.py, mastery_listener và simulate_students.py --serve-demo; gọi simulate_students.py --prepare-demo để nạp rubric minh họa và phát hành cây qua API GV. Chỉ dùng CSDL demo riêng; đây là dữ liệu giả lập, không phải kết quả đo AI.
- C2-13 chưa merge: nếu heatmap trả đúng 501 NOT_IMPLEMENTED của C2-13, trả heatmapVerified=false và weakColor=null sau khi kiểm my-map đủ 30 SV. Mọi lỗi heatmap khác vẫn fail.
- Test Postgres thật dùng schema/transaction riêng trong CI để xác nhận đủ 330 ô, 30 SV, phiên/evaluation hoàn tất và N5 9/21. Đang chờ CI trên PR; theo yêu cầu không chạy thêm test local.
## KT-06 – kiểm thử MX2 qua stack CI

- Tiên quyết C1-07 (#7, PR #119) và GD-07 (#63, PR #123) đã merge. Chuyển spec và bootstrap từ whybi-ai 9666a4c, giữ workflow E2E hiện tại có bắt lỗi.
- Chạy desktop + mobile qua Playwright: đăng nhập thật, tạo lớp/cây/rubric và phát hành qua API GV, gửi lời giảng trên SV-04, đo paste/typing, 3–5 câu phản biện, đọc điểm 5 tiêu chí và kết quả; kiểm mở khóa qua my-map.
- TC06: API từ chối nút khóa; TC08: jailbreak có cờ và không cộng điểm; TC09: hoàn tất và mở nút con; TC10 tương đương: điểm đủ nhưng thiếu ý bắt buộc vẫn FAILED theo BR-03.
- GD-06/SV-03 chưa merge: tạo phiên qua API và truyền router state đúng hợp đồng của SV-04, không tuyên bố đã test luồng bấm từ bản đồ. GD-08/SV-06 chưa merge: xác nhận API kết quả và href, chưa kiểm giao diện kết quả. TC07 giọng nói/STT chờ C1-12 và GD-08.
- Bootstrap chỉ tự seed stack Docker localhost với APP_ENV=dev|test, LLM_MODE=fake; khóa Postgres tránh seed đồng thời. Bản deploy test ngoài CI phải cung cấp KT06_COURSE_ID của môn đã seed.
- Dữ liệu/lớp được tạo riêng cho mỗi ca; trace, screenshot và kết quả JSON trong artifact playwright-report. Chưa có bằng chứng trên VM thật. Không chạy test local; chờ GitHub CI và Long duyệt.
- Lỗi tải lại SV-04 đã có issue #79; không đóng hoặc coi đã sửa trong KT-06.
## KT-08 – bảo mật và phân quyền

- C2-07 đã merge. Chuyển bộ test phù hợp API hiện tại từ whybi-ai@4d48966: JWT thật, Argon2id, ma trận vai trò viết tay và Postgres kiểm dữ liệu theo lớp/người.
- C1-07 đã có: bỏ xfail cho kiểm quyền kết quả phiên và gửi lượt. Các endpoint C2-13/C2-17/C2-20/C1-12 chưa có vẫn xfail(strict=True) với lý do cụ thể, tự báo XPASS khi triển khai xong.
- Sửa my_map kiểm ghi danh trước khi đọc cây, để SV ngoài lớp nhận 403 ngay cả khi cây chưa phát hành; cần Long rà thay đổi services/mastery.py.
- Không test local. Theo Quyền, tạo PR thường; đóng #47 khi tất cả GitHub checks pass, không coi đây là xác nhận CD/VM.
### KT-08 – bổ sung phụ thuộc xác thực WebSocket

- CI PR #135 lỗi chung backend/E2E do main port realtime.py (C1-09) import user_from_token nhưng deps.py chưa có hàm này.
- Lấy đúng deps.py từ whybi-ai@75145a4: HTTP và WebSocket dùng chung verified_claims và xử lý token không phải chuỗi bằng INVALID_TOKEN. Không kéo phần thu hồi theo user của C2-19 chưa có.
- Theo Quyền: không test local và không chờ/chạy lại CI thủ công; sửa từ nguồn rồi push cùng PR. Chưa tuyên bố bản sửa đã pass CI.

## KT-11 – MX3/MX4 và realtime

- C2-13, C2-14, GD-10, GD-11 đã merge. Chuyển test backend/E2E từ whybi-ai@5a3eb84; không mang biên bản đo cũ sang.
- Kiểm heatmap theo mẫu, truy vết gốc, ghép cặp 6.6.4, opt-in/từ chối/xác nhận lại và cập nhật nhất quán. Test realtime dùng Hub probe; E2E dùng nginx/API/Redis/Celery/WebSocket thật với LLM fake.
- Orchestrator truyền pass_threshold của lớp vào Judge để ngưỡng 70/90 được áp đúng khi chấm, giữ các điều kiện BR-03 khác.
- Chưa có video hay biên bản chạy demo thật của repo mới. Artifact CI giữ bằng chứng của test, không thay thế diễn tập 7 phút hoặc đo chất lượng AI.
- Không test local; PR thường, đóng #50 khi toàn bộ checks GitHub pass theo Quyền. Không xử lý KT-08/KT-12 đang có người khác phụ trách.
## KT-07 – bộ chạy Guard và báo cáo CI

- C1-06 (#6) đã merge, đủ tiên quyết bắt đầu. Chuyển runner/test từ whybi-ai@62802b3, không mang số liệu cũ sang.
- CI chạy 58 kịch bản với Guard thật và FakeProvider, tạo artifact kt07-guard-report. --ci-smoke chỉ kiểm >=50 ca không lỗi; chất lượng vẫn có thể chưa đạt và được ghi rõ trong báo cáo.
- Repo không có Actions secrets để chạy model thật. Chưa đo Đạt sai qua phiên; --judge hiện chấm trực tiếp, không đại diện toàn bộ C1-07. Dữ liệu còn cần rà độc lập. Giữ PR draft, chưa đóng #46 khi chưa đủ bằng chứng.
- Không chạy test hoặc evaluation local theo yêu cầu. Long duyệt thay đổi workflow; chỉ chạy lại CI nếu có lỗi.


- Cập nhật: tiếp tục kiểm GitHub CI đến khi pass theo yêu cầu mới; không chạy test local.

### KT-08 – hoàn tất merge và sửa cấu hình phiên

- Đã hoàn tất merge do pull đang dở và giữ các thay đổi của cộng tác viên trên remote KT-08.
- Sửa get_settings dùng mặc định 3 câu khi model ClassSection chưa có challenge_count; nếu thuộc tính đã có thì giữ giá trị cấu hình. Thêm hai ca hồi quy cho cả hai dạng model.
- Tiếp tục theo dõi GitHub CI đến khi backend/E2E/Docker pass; không chạy test local. Không xử lý KT-12 vì người khác đang phụ trách.