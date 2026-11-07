# docs/status/dang.md   (chỉ Đăng sửa)

> Cập nhật sau mỗi thẻ (kế hoạch §4.2). Mọi người – và mọi phiên AI – đọc hết `docs/status/` trước khi sửa code.

- Xong: C1-01 – chốt hợp đồng phiên `backend/app/models/schemas/session.py` (test `tests/unit/test_session_schema.py`).
- Phát sự kiện / hợp đồng đã chốt:
  - **Hợp đồng #2 – phiên** (`app/models/schemas/session.py`), JSON camelCase:
    - `SessionStart` (POST /sessions): `nodeId`, `inputMode`, `ttsEnabled`, `peerMatchItemId?`.
    - `SessionCreated`: `sessionId`, `status`, `opening: Question`.
    - `Turn` (POST /sessions/{id}/turns): `turnType` chỉ `EXPLANATION | ANSWER`; `text` 1–20 000 ký tự, không rỗng;
      `inputMode=VOICE` bắt buộc `audioRef`; `sttConfidence`, `pasteRatio` ∈ [0,1]; `typingCps`, `responseTimeMs` ≥ 0.
    - `TurnReply`: `status`, `question?`, `notice?`, `questionsAsked ≤ questionsTotal`.
    - `Question` (kênh `session:{id}` → `session.question`): `text` 1–1000 ký tự, `strategy?` (None = câu mở đầu),
      `targetPointId?`, `audioUrl?`, `deadline?`.
    - `Transcript` (POST /sessions/{id}/audio): `text`, `confidence` ∈ [0,1], `words: [{word, confidence}]`,
      `lowConfidenceWords`, `audioRef`, `needsConfirmation`.
    - `JudgeResult` (đầu ra Judge, ép JSON cho LLM): `criteria` = **đúng 5** `CriterionScore {code, score 0–100, rationale?, evidence?}`,
      mỗi mã một lần; `coveredPoints`, `missingPoints` (id "KP…"), `misconceptions: [{id, corrected, evidence?}]`,
      `passedChallenges ≤ totalChallenges?`, `strengths`, `reviewHints`, `judgeRuns ≥ 1`.
      Hàm: `total_score(weights)` = Σ wᵢ·sᵢ; `weighted_criteria()` → `CriterionResult`; `check_pass(rubric, pass_threshold?, min_passed_challenges?, weights?)` → `PassCheck` theo **BR-03**.
    - `PassCheck`: `verdict`, `totalScore`, `passThreshold`, `missingRequiredPoints`, `passedChallenges`,
      `minPassedChallenges`, `uncorrectedCriticalMisconceptions`, `failedConditions ⊆ {SCORE, REQUIRED_POINTS, CHALLENGES, CRITICAL_MISCONCEPTION}`.
    - `CriterionResult` (hiển thị SV/GV, ví dụ 5.4.4): `code`, `weight` ∈ [0,1], `score` ∈ [0, max], `max = weight·100`.
    - `SessionResult` = GET /sessions/{id}/result **và payload `session.completed`**: `sessionId, studentId, nodeId, classId,
      state, verdict, totalScore ∈ [0,100], passThreshold, criteria, strengths, reviewHints, sourcePages, unlockedNodes,
      flags (FlagType), isPeerFollowup, detectedMisconceptions, completedAt?`.
    - `DEFAULT_CRITERION_WEIGHTS` (Bảng 6.4): 0,25 / 0,25 / 0,20 / 0,20 / 0,10.
  - Quy ước điểm: Judge chấm 0–100 mỗi tiêu chí; kết quả hiển thị quy về điểm có trọng số (22/25…); tổng 0–100.
  - `LLM_MODE=fake`: schema có `examples` (JSON Schema) thì fake trả ví dụ đó → `call_json(JudgeResult, …)` hợp lệ.
- C1-02: đã chuyển LLM Gateway và provider Gemini / OpenAI-compatible; đang kiểm chứng CI.
  - `call_json` kiểm schema, thử lại, chuyển model dự phòng; hỗ trợ cache và ngân sách token phiên qua Redis.
  - QTV đổi cấu hình LLM qua `PUT /admin/ai-config`; cấu hình ghi đè hiện chỉ trong tiến trình.
  - Thêm `google-genai` theo lockfile; bổ sung cấu hình timeout, retry, cache và embedding.
  - Phần STT/TTS và quản trị khác giữ cho các thẻ sau; `FakeProvider` bổ sung `model` theo hợp đồng gateway.
- Đang làm: C1-02 – chờ kết quả CI và Long duyệt PR.
- Cần từ người khác:
  - Long: rà hợp đồng phiên (đồng chủ `session.py`); MasteryService (C2-10) nghe `session.completed` với payload `SessionResult` ở trên.
  - Thắng: chạy `npm run gen:api` sau khi PR C1-01 merge (đã thử sinh kiểu từ OpenAPI + `tsc` không lỗi).

- C1-03: đã port câu mở đầu Tutee đúng vai từ repo gốc; Guard kiểm đầu ra, sinh lại tối đa 2 lần và dùng câu mẫu khi cần. Bổ sung prompt registry và prompt Guard làm phụ thuộc. Local: 205 passed, 6 skipped; chờ CI và Long duyệt PR.

- C1-04: đã port phân tích coverage và chọn 4 chiến lược phản biện, giới hạn 3–5 câu; Guard kiểm câu hỏi và câu dự phòng. Helper transcript dùng chung đặt trong ai/prompts. Local: 278 passed, 12 skipped; chờ CI và Long duyệt PR.

- C1-05: port Judge chấm 5 tiêu chí, BR-03, chấm nhiều lần và phản hồi từ whybi-ai@40ae7a7; chờ CI và Long duyệt.

- C1-06: port Guard từ whybi-ai@b40440d: mở rộng luật injection, cờ GUARD_UNCHECKED khi LLM sập, kiểm câu dự phòng. Kèm ngưỡng dán/tốc độ gõ là phụ thuộc của Guard nguồn; chưa nối orchestrator C1-08. Local 394 passed, 14 skipped; chờ CI và Long duyệt enum/config.

## C1-18 / #145 – embedding fake sau port

- Đã khôi phục embedding băm 768 chiều, xác định và chuẩn hóa cho FakeProvider; helper _hash_embedding đáp ứng test RAG/cây đã port.
- Hồi quy trước sửa: test_fake_embeddings_are_normalized_and_deterministic đỏ vì vector toàn 0. Sau sửa: test_fake_gateway.py + test_tree_builder.py có 18 passed; Ruff check/format xanh.
- Toàn bộ tests/ai: 275 passed, 3 failed trong test_demo_mode.py do phần nối fallback C1-13 còn thiếu ở Tutee/Judge. Không quy số liệu fake thành đánh giá AI thật.
- #145 chưa xong: còn phần nối C1-09/STT/TTS/timer và phụ thuộc C2. Nhánh này không thay schema, migration hay code của thành viên khác; không merge.

## C1-13 – nối lại demo dự phòng khi LLM mất mạng

- Khôi phục đúng các điểm gọi fallback đã có trong app.ai.demo: mở đầu/câu hỏi/coverage Tutee và một lượt chấm Judge, chỉ khi DEMO_MODE=1 và LLM_UNAVAILABLE.
- Test hồi quy trước sửa: 3 lỗi trong test_demo_mode.py. Sau sửa toàn bộ tests/ai có 286 passed; thêm 8 ca bảo đảm không nuốt lỗi ngân sách token/cấu hình.
- Giữ nguyên Guard, cách bọc transcript, hợp đồng, model và migration. LLM_MODE=fake không phải số liệu đánh giá model thật.
- Phụ thuộc PR embedding trên fix/145-c1-embedding; chưa merge hoặc đóng thêm issue.
- Review độc lập phát hiện fallback câu hỏi từ rubric có thể xác nhận đáp án/giảng hộ khi mất LLM; đã thêm 2 ca tái hiện đỏ và áp role_violation trước trả fallback. Toàn bộ tests/ai sau sửa: 288 passed; Ruff xanh.

## Bàn giao phần C1 – các PR chờ Đăng/Long review

- #147: giáo trình và jobId/quyền kênh tiến độ; khôi phục test preprocess đã sửa.
- #148: API STT và consent. #149 xếp trên #148: TTS private và audioUrl khi bật. Thắng có thể review phần nối SV-05; Quyền chuẩn bị kiểm thử giọng nói sau khi #148 và GD-08 được merge.
- #150: embedding fake và demo fallback; khôi phục test_demo_mode.py (288 test AI xanh). Đã tiếp nhận main #146, không thay danh sách skip ngoài những module có bản sửa và kiểm chứng tương ứng.
- C1-15 (#15) còn cần Long chốt ClassSection.challenge_count, ClassService.get_settings, answer_time_limit_s=120 và answer_grace_s=10. Không tự sửa model/migration/config C2.
- Cây/rubric còn cần Long nối SkillTreeService.get_node_for_session/node_for_edit và endpoint regenerate_rubric; giữ các test phụ thuộc này tạm bỏ qua như #146.
- STT thật cần số liệu p95 từ ghi âm thực; server chưa kiểm được thời lượng audio nén (WAV đã có). Không ghi số liệu fake thành kết quả thực nghiệm.
- Không merge, auto-merge, đóng issue hoặc sửa main trong phiên này. Các PR để draft cho tới khi đủ kiểm chứng; #145 vẫn còn phần cần phối hợp.
