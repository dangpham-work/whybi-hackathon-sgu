# Kế hoạch cải thiện MX1 – cây kỹ năng

> Nguồn: khảo sát 2026-11-08 (backend, pipeline AI, giao diện) + đo thật trên 2 giáo trình PDF
> (Cần Thơ 109 trang, Lê Minh Hoàng 316 trang). Số dòng đã kiểm lại trên worktree `feat/cay-tu-de-cuong`.

## 0. Quyết định đã chốt

| Câu hỏi | Chọn | Lý do |
|---|---|---|
| Thứ tự | **PR0 → A → B → E1 → D → C** | A là lỗi đang làm hỏng demo; B là chất lượng lõi; D (duyệt cây lớn) cần cho demo hơn gộp nút |
| Gộp nút | **Gộp trên bản nháp + lưu `aliases` (key cũ) ở nút giữ lại**; `MasteryService` khi phát hành ghép ô theo key **hoặc** alias | Đủ đúng (không mất thành tích SV) mà chỉ thêm 1 cột; không cần bảng ánh xạ riêng |
| Sửa thư mục người khác | **Tự làm hết**, mỗi PR ghi rõ phần đụng thư mục ai và tag người đó duyệt | Hackathon, Long gác merge; viết việc cho người khác chậm hơn tự làm |
| Đổi schema | **Có, gộp vào 1 migration duy nhất** (đợt B): `tree_nodes.source_page_start`, `source_page_end` (int, null), `aliases` (JSONB, mặc định `[]`) | Một lần đổi hợp đồng `models/schemas/tree.py`, Long tạo migration |
| Không làm | Undo/redo, so sánh phiên bản tô lên cây, kéo thả tệp, trích dẫn từng ý, `source_chunk_id` | Không ảnh hưởng demo; ghi lại ở §8 |

Quy tắc chung mỗi PR: test viết trước (đỏ) → code → `ruff check`, `ruff format --check`, `pytest` (cả test DB,
chạy **riêng từng file đụng tới** và **cả bộ**, vì đã gặp test chỉ xanh khi chạy chung) → frontend
`typecheck`, `test`, `build` → commit `<mã-thẻ>: …` → PR `Closes #…`.

## 1. Chuỗi nhánh / PR

```
main
 └─ PR0 feat/cay-tu-de-cuong        C1-19  port cảnh báo mục lục (backend) + hiệu chỉnh hằng số   [ĐÃ CODE, chưa commit]
     └─ PR-A1 fix/mx1-luong-dung-cay  C2-22  lỗi luồng job / rubric (backend)
         └─ PR-A2 fix/mx1-gv03-gv04     GD-18  lỗi GV-03 báo xong sớm, kéo nút, Backspace (frontend)
             └─ PR-B feat/c1-20-chat-luong-cay  C1-20  ứng viên tiên quyết, gộp trùng, prompt, trang nguồn, RAG theo tài liệu + migration
                 └─ PR-E1 feat/gd-19-chon-chuong  GD-19  TocPanel / GV-03 / GV-04 chọn chương (port đợt 2)
                     └─ PR-D feat/gd-20-cay-lon     GD-20 + C2-23  duyệt cây lớn, duyệt hàng loạt, phát hành có kiểm tra
                         └─ PR-C feat/c2-24-xoa-gop-nut  C2-24 + GD-21  xóa / gộp nút, chu trình tô đường, cạnh AI
```

PR xếp chồng vì cùng đụng `documents.py`, `GV03/GV04`. Merge từ dưới lên, rebase sau mỗi lần merge.
Thẻ mới thêm vào `docs/cards/<người>.md` trong chính PR đó.

## 2. PR0 – C1-19 (đã code)

Còn lại: viết `docs/status/dang.md` (nhờ Đăng hoặc ghi trong PR), commit làm 2 commit:
(1) port nguyên từ whybi-ai@a040c29..851235a, (2) hiệu chỉnh `CHARS_PER_CHUNK=7000`,
`NODES_PER_CHUNK={4,8,11}`, giữ `MAX_CONCEPTS=12/TOP_SIMILAR=3/MAX_CANDIDATES=6`. PR mô tả số đo thật.

## 3. Đợt A – lỗi đang làm hỏng luồng

### PR-A1 (C2-22, backend)

| # | Lỗi (bằng chứng) | Sửa | Test viết trước |
|---|---|---|---|
| A1 | `SyllabusService.cancel` đặt `FAILED` vô điều kiện (`services/syllabus.py:343-344`) ⇒ không `request_build` lại được (đòi PARSED, `:314`), mất đoạn RAG (`retrieval.py:128`) | Nếu `doc.status == PARSED` (hủy lúc dựng cây) thì **giữ PARSED**, chỉ ghi `error_message="Đã hủy dựng cây"`; còn đang bóc chữ thì FAILED như cũ | `test_huy_luc_dung_cay_van_dung_lai_duoc` (DB): hủy sau PARSED ⇒ status PARSED, `build-tree` trả 202 |
| A2 | Cờ `job:{id}:cancelled` TTL 1 h, không ai xóa (`workers/documents.py:346`); job dựng lại dùng chung `job_id=doc.id` (`syllabus.py:328`) | Thêm `uncancel(job_id)` vào `JobProgressSink`/`RedisJobProgress`/`InMemoryJobProgress`; gọi trong `request_build` và `upload` trước khi enqueue | `test_dung_lai_sau_huy_khong_bi_huy_ngay` (unit, InMemory) |
| A4 | `_rubrics` chụp danh sách nút đầu (`documents.py:743`) rồi `put_rubric` không kiểm lại (`:756`) ⇒ ghi đè rubric GV vừa sửa/duyệt; luồng dựng đầy đủ `only_missing=False` (`:695`) cũng vậy | Thêm tham số `only_if_missing=True` cho `SkillTreeService.put_rubric` dùng nội bộ: dưới khóa `FOR UPDATE` đã có, nút đã có rubric ⇒ bỏ qua, trả `None`. Worker luôn gọi chế độ này | `test_ai_khong_ghi_de_rubric_gv_vua_duyet` (DB): GV `put` rubric giữa lúc gateway giả đang chờ ⇒ rubric GV còn nguyên |
| A5 | `generate-missing` enqueue mỗi lần bấm (`syllabus.py:296-297`) | Redis `SET job:fill:{class_id} NX EX 900` trong `request_fill_rubrics`; đang có ⇒ 409 `FILL_IN_PROGRESS`; task xóa khóa ở `finally`. InMemory queue dùng set | `test_bam_sinh_bu_hai_lan_tra_409` |
| A6 | `POST /nodes/{id}/rubric/regenerate` còn `NotImplementedYet("C1-11")` (`api/trees.py:78-81`); `services/rubric.py:27` gọi `trees.node_for_edit` không tồn tại; `tests/unit/test_rubric_db.py` 2 test đỏ khi chạy riêng file | Thêm `SkillTreeService.node_for_edit(node_id, user) -> (class_id, Node)` dùng lại `_version` + kiểm chủ lớp; nối router gọi `regenerate` | 2 test có sẵn phải xanh khi chạy **riêng file**; tìm vì sao chạy chung lại xanh (nghi monkeypatch router rò từ test khác) và sửa cho cô lập |
| A9 | Lỗi truy hồi/nhúng sau khi cây đã commit làm FAILED cả job (`documents.py:684-692, 746-750`) | Bắt lỗi theo nút như bước generate; job vẫn DONE, `error_message` = "N nút chưa có rubric – bấm Sinh rubric bù"; xóa `error_message` cũ khi thành công (`:693-699`) | `test_loi_truy_hoi_mot_nut_khong_lam_hong_job` |

### PR-A2 (GD-18, frontend)

| # | Lỗi | Sửa | Test |
|---|---|---|---|
| A3 | `GV03.tsx:79` coi `DONE` đầu tiên (bóc chữ, `documents.py:423`) là xong; `STEP_LABEL` thiếu bước; chỉ nghe `job.progress` | `done` = đã nhận `tree.generated`; thêm nhãn CONCEPTS/DEDUPE/PREREQUISITES/TREE/INDEXING/RUBRICS/AWAITING_SELECTION/CANCELLED; lưu `documentId`; thêm nút **Hủy** gọi API có sẵn (`api/classes.py:147`); lỗi hiện `error_message` thật | sửa `gd05.test.tsx:92-94` (đang chốt hành vi sai) + test mới: DONE bóc chữ chưa hiện link, `tree.generated` mới hiện |
| A7 | `tree-layout.ts:27` chỉ dùng vị trí lưu khi **mọi** nút có tọa độ ⇒ kéo nút trên cây AI bị xếp lại; thêm nút mất layout tay | Chạy dagre cho cả cây rồi **ghi đè** bằng tọa độ đã lưu với nút có `positionX/Y` | `SkillTree.test.tsx`: cây 3 nút, 1 nút có tọa độ ⇒ nút đó giữ đúng tọa độ |
| A8 | Không đặt `deleteKeyCode` ⇒ Backspace xóa nút giả | `deleteKeyCode={null}` | test bấm Backspace, nút vẫn còn |
| A10 | Lưu vị trí lỗi bị nuốt (`GV04.tsx:93`) | Hiện ErrorBox "Không lưu được vị trí" | test 409 |

## 4. Đợt B – chất lượng cây AI (PR-B, C1-20)

**Bước 0 – đo trước (B7).** Script `evals/tree/dung_that.py` (thư mục của Quyền, ghi trong PR): chạy
TreeBuilder thật trên N đoạn đầu của mỗi chương của 2 PDF, in: số nút, số cạnh trước/sau rút gọn bắc cầu,
cạnh/nút, cặp nút trùng tên chuẩn hóa, số lượt `call_json` + `embed`, thời gian. Lưu kết quả
`evals/results/tree-dung-that.md`. Chạy **trước** và **sau** B1–B4 với cùng tham số (≈ 300 lượt
gpt-4o-mini mỗi lần). Mốc hiện tại (3 đoạn): 33 nút / 76–82 cạnh ở DETAILED.

| # | Vấn đề (bằng chứng) | Sửa | Test (gateway giả, `tests/ai/test_tree_builder.py`) |
|---|---|---|---|
| B1 | Luôn lấy `TOP_SIMILAR` nút gần nhất dù không liên quan (`tree_builder.py:193`) | Thêm `MIN_CANDIDATE_COSINE = 0.35` (hiệu chỉnh bằng bước 0); `near` chỉ giữ nút vượt ngưỡng; không ứng viên ⇒ không gọi LLM | nút không liên quan (cosine thấp) ⇒ 0 lượt `_judge` |
| B2 | "Được nhắc tên" bằng chuỗi con (`:192`); cắt `[-MAX_CANDIDATES:]` theo chỉ số (`:194`) | So **theo từ nguyên vẹn** trên chuỗi đã chuẩn hóa (`\b` + NFC casefold); xếp ứng viên theo (được nhắc tên trước, rồi cosine giảm dần), cắt `[:MAX_CANDIDATES]` | "Mảng" không khớp "mảng băm động" khi tên là "Mảng băm"; ứng viên gần nhất luôn được giữ |
| B3 | Gộp chỉ so bản sao **đầu tiên** ≥ 0,9 (`:162`); trùng key thì đổi `_2` (`:165-168`) | (1) Tên chuẩn hóa trùng nhau ⇒ gộp luôn, không cần LLM; (2) cosine: lấy bản **giống nhất**; (3) gộp thì nối mô tả nếu bản giữ quá ngắn; vectơ dùng lại cho B1 (bỏ embed lần 2, `:188`) | 2 khái niệm cùng tên khác mô tả ⇒ 1 nút; embed gọi 1 lần |
| B4 | AI lấp đầy trần (`prompts/tree_concepts.md:11`) | Prompt: "chỉ khái niệm cốt lõi SV phải giải thích được; ít hơn {max} là bình thường; không tách ví dụ / định lý phụ thành khái niệm"; giữ cắt cứng | test prompt render có câu mới (đo thật ở bước 0) |
| B5 | Nút không có trang nguồn; `chapter_ref` chữ tự do của LLM (`schemas/tree.py:61`, `tree_builder.py:41,249`) | `Chapter` mang `start_page/end_page` (từ `[Trang n]` đã có); `Concept` nhận trang của đoạn; **`chapter_ref` lấy từ mục lục TocStep** (đọc `toc.json`) nếu có, không thì từ `split_chapters`, bỏ trường LLM. Migration: `source_page_start`, `source_page_end`, `aliases` | nút mang đúng khoảng trang của đoạn; chapter_ref trùng tiêu đề mục lục |
| B6 | RAG rubric lấy đoạn mọi tài liệu PARSED của lớp (`services/retrieval.py:121-131`) | `retrieve(..., document_id=None)`; worker truyền tài liệu đang dựng; sinh lại 1 nút dùng tài liệu tạo bản nháp (kiểm lúc code `tree_versions` có lưu `document_id` chưa; không có thì lấy tài liệu PARSED mới nhất) | lớp 2 tài liệu ⇒ rubric chỉ trích tài liệu A |
| B8 | Mức chi tiết mặc định lệch: tự động 12, GV chọn 8 (`documents.py:606`, `syllabus.py:309`) | Thống nhất `DEFAULT_DETAIL="STANDARD"` (8) cho cả hai đường, sửa `estimate_size` mặc định theo | test cùng mặc định |
| B9 | Gộp LLM chạy tuần tự (`:161-181`); cosine Python thuần O(n²·d) | Ma trận cosine bằng `numpy` nếu đã có trong `uv.lock` (không thì giữ Python, đo trước); câu hỏi `_same` chạy bằng ThreadPool | thời gian dedupe 300 khái niệm < 2 s (gateway giả) |

Tiêu chí xong đợt B: trên cùng bộ đo, **cạnh/nút giảm ≥ 40 %**, số nút trùng tên = 0, số lượt AI không tăng;
`evaluate.py` cây CTDL vẫn không giảm F1 cạnh.

## 5. Đợt E1 – chọn chương ở giao diện (PR-E1, GD-19)

Port từ `whybi-canh-bao-muc-luc` (`git diff a040c29^ 851235a -- frontend`): `components/TocPanel.tsx`,
`lib/syllabus-scope.ts`, sửa `GV03.tsx`, `GV04.tsx`, `lib/api-types.ts` (sinh lại bằng `npm run gen:api`,
không chép tay), test `toc-scope.test.tsx`, `toc-gv04.test.tsx`.
Chèn vào GV-03 sau khi A3 xong: nhận `syllabus.toc_ready {gated:true}` ⇒ hiện TocPanel thay vì thanh tiến
độ; gửi `build-tree {ranges, detail, lazyRubric}`; ước tính trực tiếp lấy `charsPerChunk`/`nodesPerChunk`
từ báo cáo (đã hiệu chỉnh). Kiểm tay trên 2 PDF thật qua Docker: Cần Thơ ra TOO_LARGE ở DETAILED, chọn
1 chương ⇒ ước ≈ 60 nút.

## 6. Đợt D – cây lớn và quy trình duyệt (PR-D: GD-20 frontend + C2-23 backend)

| # | Việc | Chi tiết |
|---|---|---|
| D1 | Khung vẽ | Nút "Toàn màn hình" (GV-04 đang cố định `height={420}`, `GV04.tsx:207`); `MiniMap`; `minZoom 0.1`; `onlyRenderVisibleElements`; nút **Tự sắp xếp** (xóa tọa độ lưu ⇒ dagre ⇒ PATCH hàng loạt) |
| D2 | Trạng thái rubric trên nút | Prop `rubricLook` cho SkillTree: chưa có / chưa duyệt / đã duyệt – màu **kèm biểu tượng + chữ** (`lib/status.ts`); chú giải riêng cho chế độ edit (bỏ chú giải mastery sai ngữ cảnh, `SkillTree.tsx:221`), chú giải nét đứt = cạnh AI |
| D3 | Tìm và lọc | Ô tìm theo tên/mã ⇒ `fitView` vào nút; lọc theo chương (`chapter_ref` sau B5) và theo trạng thái rubric; danh sách "N nút chưa duyệt" thành danh sách bấm được (thay chuỗi nối `GV04.tsx:215`) |
| D4 | Duyệt hàng loạt | Backend `POST /classes/{id}/tree/rubrics/approve {nodeIds}` (C2-23): chỉ duyệt rubric **hợp lệ** (≥ 1 ý bắt buộc có nội dung, `len(scenarios) ≥ min_challenges`), trả `{approved, rejected:[{nodeId, reason}]}`; UI: chọn nhiều / "Duyệt cả chương" |
| D5 | Kiểm rubric hợp lệ | Một hàm `rubric_problems(r) -> list[str]` trong `services/skill_tree.py` dùng chung cho `put_rubric(approved=True)` (422 `RUBRIC_INVALID`), duyệt hàng loạt và `publish`; UI khóa nút "Duyệt" khi rỗng (`RubricEditor.tsx:117`) |
| D6 | Phát hành có kiểm tra | `GET /classes/{id}/tree/publish-check` (C2-23) trả nút thiếu/chưa duyệt/không hợp lệ, số SV bị ảnh hưởng, bản nháp có cũ hơn bản đang phát hành không; UI hộp xác nhận + ô `changeNote`; lỗi hiện một lần, không JSON thô (`tree-edit.ts:268`, `GV04.tsx:177-184`) |
| D7 | Hiệu năng | `flowNodes` tách layout (deps: nút/cạnh) khỏi tô chọn (deps: `selectedKey`) (`SkillTree.tsx:140-175`); `list_versions` trả tóm tắt (id, số, trạng thái, ngày, số nút/cạnh, ghi chú) – thêm schema `TreeVersionSummary` (C2-23), N+1 ⇒ 1 truy vấn đếm |
| D8 | GV-04 lúc chưa có cây / đang sinh | 404 ⇒ link sang GV-03; `GENERATING` ⇒ "AI đang dựng cây" thay vì mời tạo bản nháp (`GV04.tsx:152-159`); nhãn trạng thái dùng `TREE_STATUS` |
| D9 | Busy riêng | `busy` theo thao tác (lưu nút / rubric / sinh lại AI) thay cờ chung (`GV04.tsx:32`) |

Test: backend DB cho D4–D7; frontend cho D2–D6, D8 (Vitest + Testing Library như `gd09.test.tsx`).

## 7. Đợt C – thao tác sửa cây (PR-C: C2-24 backend + GD-21 frontend)

| # | Việc | Chi tiết |
|---|---|---|
| C1 | Xóa nút | `DELETE /nodes/{id}?bridge=true` (C2-24): khóa cây, xóa nút (cascade cạnh/rubric); `bridge=true` nối mọi cha→con trừ khi tạo cạnh bắc cầu thừa; trả `{removedEdges, bridgedEdges}`. Không xóa nút trên bản đã phát hành (409 `TREE_NOT_EDITABLE` như các thao tác khác). UI: hộp xác nhận có ô "nối lại tiên quyết" |
| C2 | Gộp nút | `POST /classes/{id}/tree/nodes/merge {keepId, mergeIds[]}`: chuyển cạnh vào/ra sang nút giữ (bỏ tự vòng, bỏ trùng, kiểm chu trình – trả path nếu có), rubric giữ của nút giữ (nút giữ không có thì lấy của nút gộp đầu tiên có rubric, `approved=false`), `aliases += keys gộp`, xóa nút gộp. `MasteryService` migrate (`mastery.py:213-237`): ô cũ có key ∈ `aliases` của nút mới ⇒ chuyển sang nút đó, lấy trạng thái cao nhất. UI: chọn nhiều nút (Shift+click) ⇒ "Gộp vào…" |
| C3 | Tô đường chu trình | SkillTree nhận `highlightPath: string[]` ⇒ nút/cạnh trên đường viền đỏ + biểu tượng; lấy từ `details.path` (`tree-edit.ts:257-262`) |
| C4 | Cạnh AI | Cạnh `confidence < 0.75` tô cam + nhãn "AI chưa chắc"; panel cạnh: "Xác nhận" (PATCH `source=LECTURER` – thêm endpoint `PATCH /edges/{id}` C2-24) / "Xóa"; `ariaLabel` dùng tên nút; lọc "chỉ cạnh AI chưa xác nhận" |
| C5 | Rubric editor | Sinh lại khi `dirty` ⇒ hỏi; trạng thái "AI đang sinh…" + timeout 90 s; sửa được tình huống phản biện, `probeQuestion`, `isCritical`; kiểm số (`Number("")` = 0, `RubricEditor.tsx:91,95`) |
| C6 | An toàn thao tác | Đổi nút khi còn bản sửa chưa lưu ⇒ hỏi; xác nhận xóa cạnh; thêm tiên quyết bằng ô chọn (không chỉ kéo); mở panel bằng Enter (bàn phím) |
| C7 | Lỗi 500 tiềm ẩn | `TreeVersion._check_keys` chặn cạnh trùng (`schemas/tree.py:100-113`); `max_length` khớp cột (`key` 64, `code` 8, `chapter_ref` 100, id KP/MC/SC 8); `delete_edge` khóa trước khi đọc (`skill_tree.py:643-649`); `transitive_reduction` không bỏ cạnh LECTURER (`dag.py:70-76`) |
| C8 | Mất cập nhật hai tab | `PATCH /nodes`, `PUT /rubric` nhận `If-Match: <updatedAt>` (tùy chọn); lệch ⇒ 409 `STALE_WRITE`; UI tải lại nút và báo |

## 8. Để sau (ghi lại, không làm trong chuỗi này)

Undo/redo; so sánh phiên bản tô lên cây; kéo thả tệp ở GV-03; trích dẫn trang theo từng ý chính +
`source_chunk_id`; lưu tạm `concepts.json` để thử lại không mất token, idempotent khi Celery chạy lại
(`acks_late`, `celery_app.py:34`) – làm nếu demo gặp worker chết; cache embedding ở gateway; eval cây
trong CI (cần cây chuẩn GV xác nhận); chế độ demo thay cây thật bằng cây CTDL bất kể môn
(`documents.py:676-680`) – báo GV thay vì im lặng.

## 9. Rủi ro và cách giảm

| Rủi ro | Giảm |
|---|---|
| Migration đợt B đụng dữ liệu dev đang có | Cột mới đều nullable / mặc định `[]`; `alembic check` + chạy lên DB tạm trước |
| B1–B4 làm mất cạnh đúng | Bắt buộc đo trước/sau (§4 bước 0) + F1 cây CTDL không giảm; ngưỡng là hằng số dễ chỉnh |
| PR chồng dài, rebase đau | Merge PR0, A1, A2 sớm (nhỏ, độc lập logic); B trở đi mới chồng |
| Đụng thư mục Đăng/Thắng/Quyền | Mỗi PR có mục "Thư mục người khác" liệt kê file, tag chủ để duyệt |
| Chi phí AI khi đo | gpt-4o-mini, ≈ 300 lượt/lần đo, chỉ 2 lần đo |

## 10. Ước lượng

| PR | Quy mô | Thời gian |
|---|---|---|
| PR0 | đã code | 15 phút commit + PR |
| A1 | ~6 file backend, ~8 test | 2–3 h |
| A2 | ~4 file frontend, ~5 test | 1,5–2 h |
| B | ~8 file + 1 migration + script đo | 4–5 h (kể cả 2 lần đo) |
| E1 | port ~6 file frontend | 2 h |
| D | ~10 file, 3 endpoint | 5–6 h |
| C | ~10 file, 4 endpoint | 6–7 h |
