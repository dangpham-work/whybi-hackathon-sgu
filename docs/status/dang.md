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
- Đang làm: C1-02 (LLM Adapter).
- Cần từ người khác:
  - Long: rà hợp đồng phiên (đồng chủ `session.py`); MasteryService (C2-10) nghe `session.completed` với payload `SessionResult` ở trên.
  - Thắng: chạy `npm run gen:api` sau khi PR C1-01 merge (đã thử sinh kiểu từ OpenAPI + `tsc` không lỗi).
