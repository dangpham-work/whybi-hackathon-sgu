# Quy trình chi tiết: chuyển code theo đợt, theo vòng

Bổ sung cho `DE-XUAT-NGHI-TEST.md`; thay cho cách chạy tuần tự 74 lượt trong `HUONG-DAN.md`. Sinh từ dữ liệu thẻ và issue của repo `whybi-hackathon-sgu` ngày 2026-11-07. Số issue (#) là số ở repo mới; 73 thẻ giữ nguyên số #1–#73.

## Quy tắc chung

1. **Đợt** = một chức năng lớn, kết thúc bằng điểm dừng test của cả nhóm. **Vòng** = các thẻ chạy song song bên trong đợt.
2. Mỗi người làm **tối đa một thẻ mỗi vòng**. Thẻ chỉ được chạy khi **mọi thẻ nó phụ thuộc đã merge** (cột "Cần có").
3. Vòng kết thúc khi **mọi PR của vòng đã merge**. Người merge là Long (Đăng thay khi Long nghỉ). Khi xong vòng, người merge báo: "Xong đợt N vòng M".
4. Cách làm một thẻ (giữ nguyên như `HUONG-DAN.md`): `git switch main` → `git pull` → `sh ../whybi-port/port-the.sh <THẺ>` → `git show --stat HEAD` → `git push -u origin port/<thẻ viết thường>` → mở PR vào `main`.
5. **Mô tả PR phải có dòng `Closes #<số issue>`** (cột Issue) để issue tự đóng khi merge.
6. Không tự sửa file trong lúc chuyển. Gặp lỗi: ghi issue, báo nhóm, không chạy tiếp thẻ đó.
7. Cuối mỗi đợt cả nhóm dừng và test theo mục "Điểm dừng test" của đợt. Cả 4 người báo "Ổn" thì Long mới báo bắt đầu đợt sau.
8. CI đỏ giữa chừng là bình thường. Chỉ kiểm tra CI sau thẻ cuối.

### Trường hợp đặc biệt

- **`C2-01` (issue #19):** Đăng đã đẩy lên `main` (commit `5619486`). Bỏ qua thẻ này; nhóm tự quyết định ghi công, rồi đóng #19 thủ công.
- **`KHUNG-dang`, `KHUNG-thang`, `KHUNG-quyen`:** không có issue riêng (code sinh hàng loạt). PR ghi rõ là khung, không cần `Closes`.
- **`KT-15` (#54) và `GD-16` (#72):** có issue nhưng không có commit port, vì code nằm ở thẻ khác. Đóng thủ công sau khi xong đợt 6.
- **11 issue bug và đề xuất (#74–#84):** không gắn thẻ nào. Cả nhóm xử lý và đóng sau đợt 6.
- Các thẻ tổng kết (`C1-18`, `C2-21`, `KT-14`, `GD-17`, `KT-16`, `KT-17`) luôn xếp ở **cuối đợt**, vì chúng kiểm tra hoặc rà soát cả đợt.

---

## Đợt 1: Nền

Lượt cũ 1–9; 8 thẻ chạy trong 3 vòng.

### Đợt 1 – Vòng 1

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Đăng (C1 – AI) | `KHUNG-dang` | — | Khung phần Đăng (code sinh hàng loạt) | C2-01 | không cần |
| Long (C2 – backend/hạ tầng) | `C2-02` | #20 | Schema cây app/models/schemas/tree.py (Node, Edge, Rubric, TreeVersion) | — | `Closes #20` |
| Thắng (GD – giao diện) | `KHUNG-thang` | — | Khung phần Thắng (code sinh hàng loạt) | C2-01 | không cần |
| Quyền (KT – kiểm thử) | `KHUNG-quyen` | — | Khung phần Quyền (code sinh hàng loạt) | C2-01 | không cần |

Vòng này nghỉ: không ai. Vòng kết thúc khi cả 4 PR đã merge.

### Đợt 1 – Vòng 2

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Đăng (C1 – AI) | `C1-01` | #1 | Chốt schema phiên cùng Long trong app/models/schemas/session.py | — | `Closes #1` |
| Thắng (GD – giao diện) | `GD-01` | #57 | Khung giao diện: layout GV, SV, QTV; điều hướng theo sơ đồ 5.5.1; route tự nạp | — | `Closes #57` |
| Quyền (KT – kiểm thử) | `KT-01` | #40 | Mẫu issue bug (.github/ISSUE_TEMPLATE/bug.yml), nhãn P0/P1/P2 và nhãn module, bảng GitHub Projects | — | `Closes #40` |

Vòng này nghỉ: Long. Vòng kết thúc khi cả 3 PR đã merge.

### Đợt 1 – Vòng 3

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Quyền (KT – kiểm thử) | `KT-02` | #41 | Dữ liệu mẫu: lớp CTDL&GT, 1 GV, 1 QTV, 30 SV (tên giả), cây mẫu 8–10 nút theo schema của C2-02 | C2-02 (#20) | `Closes #41` |

Vòng này nghỉ: Đăng, Long, Thắng. Vòng kết thúc khi cả 1 PR đã merge.

### Đợt 1 – Điểm dừng test (cả nhóm)

Sau khi vòng cuối đã merge: mọi người `git pull` và test phần của mình. Tiêu chí lấy từ trường "Xong khi" của thẻ.

| Người | Thẻ | Issue | Xong khi |
|---|---|---|---|
| Đăng | `KHUNG-dang` | — | Các file của khung đã vào đủ (`git show --stat` khớp danh sách). |
| Đăng | `C1-01` | #1 | Schema import được; Thắng sinh kiểu TypeScript từ OpenAPI không lỗi |
| Long | `C2-02` | #20 | Đăng và Thắng lấy được cây mẫu qua API |
| Thắng | `KHUNG-thang` | — | Các file của khung đã vào đủ (`git show --stat` khớp danh sách). |
| Thắng | `GD-01` | #57 | Ba vai thấy đúng menu; mọi trạng thái có biểu tượng |
| Quyền | `KHUNG-quyen` | — | Các file của khung đã vào đủ (`git show --stat` khớp danh sách). |
| Quyền | `KT-01` | #40 | Mở thử một issue có đủ trường |
| Quyền | `KT-02` | #41 | Thư mục seed/ nạp được bằng một lệnh |

Báo vào nhóm: "Ổn" hoặc "Có lỗi" kèm link issue. Cả 4 "Ổn" thì Long báo bắt đầu đợt sau.

---

## Đợt 2: Hạ tầng, xác thực, AI nền

Lượt cũ 10–23; 14 thẻ chạy trong 6 vòng.

### Đợt 2 – Vòng 1

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Đăng (C1 – AI) | `C1-02` | #2 | LLM Adapter: nhà cung cấp Gemini và loại tương thích OpenAI, model dự phòng, ép JSON theo schema | C1-01 (#1) | `Closes #2` |
| Long (C2 – backend/hạ tầng) | `C2-03` | #21 | Docker Compose đủ dịch vụ theo Bảng 5.15 | — | `Closes #21` |
| Thắng (GD – giao diện) | `GD-02` | #58 | Kiểu dữ liệu sinh từ OpenAPI, lớp gọi API và WebSocket client dùng chung | C1-01 (#1), C2-02 (#20) | `Closes #58` |
| Quyền (KT – kiểm thử) | `KT-03` | #42 | Khung test tích hợp (pytest + httpx) và E2E (Playwright) chạy trong CI | — | `Closes #42` |

Vòng này nghỉ: không ai. Vòng kết thúc khi cả 4 PR đã merge.

### Đợt 2 – Vòng 2

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Đăng (C1 – AI) | `C1-03` | #3 | Tutee: mở đầu phiên với vai “học trò tò mò” theo nút | C2-02 (#20), C1-02 (#2) | `Closes #3` |
| Long (C2 – backend/hạ tầng) | `C2-04` | #22 | CI/CD: GitHub Actions chạy test, build image, deploy lên VM qua SSH | C2-03 (#21) | `Closes #22` |
| Thắng (GD – giao diện) | `GD-03` | #59 | Component SkillTree (React Flow) | C2-02 (#20) | `Closes #59` |
| Quyền (KT – kiểm thử) | `KT-04` | #43 | Nạp các bộ đánh giá đã chuẩn bị vào evals/ | C1-01 (#1) | `Closes #43` |

Vòng này nghỉ: không ai. Vòng kết thúc khi cả 4 PR đã merge.

### Đợt 2 – Vòng 3

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Đăng (C1 – AI) | `C1-04` | #4 | Sinh 3–5 câu hỏi phản biện theo 4 chiến lược | C1-03 (#3) | `Closes #4` |
| Long (C2 – backend/hạ tầng) | `C2-05` | #23 | Bus sự kiện Redis Pub/Sub và schema mastery.py (MasteryChanged) | C2-03 (#21) | `Closes #23` |

Vòng này nghỉ: Thắng, Quyền. Vòng kết thúc khi cả 2 PR đã merge.

### Đợt 2 – Vòng 4

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Đăng (C1 – AI) | `C1-05` | #5 | Judge: chấm 5 tiêu chí (6.3.1), công thức điểm và quy tắc Đạt BR-03 (6.3.2) | C1-02 (#2) | `Closes #5` |
| Long (C2 – backend/hạ tầng) | `C2-06` | #24 | CSDL và migration Alembic theo danh sách bảng 5.2.3, từ điển dữ liệu 5.2.4, ràng buộc DAG 5.2.5 | C2-03 (#21) | `Closes #24` |

Vòng này nghỉ: Thắng, Quyền. Vòng kết thúc khi cả 2 PR đã merge.

### Đợt 2 – Vòng 5

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Long (C2 – backend/hạ tầng) | `C2-07` | #25 | Xác thực và phân quyền | C2-06 (#24) | `Closes #25` |

Vòng này nghỉ: Đăng, Thắng, Quyền. Vòng kết thúc khi cả 1 PR đã merge.

### Đợt 2 – Vòng 6

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Thắng (GD – giao diện) | `GD-04` | #60 | Đăng nhập, quên mật khẩu, hồ sơ; SV-01 Danh sách lớp và nhập mã tham gia | GD-02 (#58), C2-07 (#25) | `Closes #60` |

Vòng này nghỉ: Đăng, Long, Quyền. Vòng kết thúc khi cả 1 PR đã merge.

### Đợt 2 – Điểm dừng test (cả nhóm)

Sau khi vòng cuối đã merge: mọi người `git pull` và test phần của mình. Tiêu chí lấy từ trường "Xong khi" của thẻ.

| Người | Thẻ | Issue | Xong khi |
|---|---|---|---|
| Đăng | `C1-02` | #2 | Đổi nhà cung cấp trong cấu hình mà không sửa code nghiệp vụ; model chính lỗi thì tự chuyển sang model dự phòng |
| Đăng | `C1-03` | #3 | Với 3 nút mẫu, câu mở đầu đúng vai và không giảng hộ |
| Đăng | `C1-04` | #4 | Với lời giảng còn thiếu ý, câu hỏi nhắm đúng ý còn thiếu trong rubric |
| Đăng | `C1-05` | #5 | Test trên bộ lời giảng có nhãn (KT-04) chạy xanh |
| Long | `C2-03` | #21 | docker compose up chạy đủ dịch vụ trên máy mới |
| Long | `C2-04` | #22 | Merge main thì bản mới tự lên VM; URL HTTPS trả /health |
| Long | `C2-05` | #23 | Test: phát sự kiện thì handler nhận đúng payload |
| Long | `C2-06` | #24 | Migration chạy sạch trên máy mới |
| Long | `C2-07` | #25 | Tài khoản SV gọi API của GV bị 403; token hết hạn sau 30 phút |
| Thắng | `GD-02` | #58 | Build không lỗi kiểu; lỗi API hiện thông báo dễ hiểu |
| Thắng | `GD-03` | #59 | Cây mẫu hiển thị đúng thứ tự tiên quyết |
| Thắng | `GD-04` | #60 | SV nhập mã 8 ký tự là vào được lớp |
| Quyền | `KT-03` | #42 | CI chạy cả test E2E |
| Quyền | `KT-04` | #43 | Script đọc được từng bộ theo schema |

Báo vào nhóm: "Ổn" hoặc "Có lỗi" kèm link issue. Cả 4 "Ổn" thì Long báo bắt đầu đợt sau.

---

## Đợt 3: Lớp học, giáo trình, cây kỹ năng, phiên giảng

Lượt cũ 24–35; 12 thẻ chạy trong 4 vòng.

### Đợt 3 – Vòng 1

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Đăng (C1 – AI) | `C1-06` | #6 | Guard: lọc đầu vào | C1-02 (#2) | `Closes #6` |
| Long (C2 – backend/hạ tầng) | `C2-08` | #26 | Lớp học phần, mã tham gia 8 ký tự, SV tham gia lớp | C2-07 (#25) | `Closes #26` |
| Quyền (KT – kiểm thử) | `KT-05` | #44 | Script giả lập 30 SV gửi kết quả qua API phiên thật, dồn lỗi vào nút N5 “Con trỏ” theo kịch bản demo | C1-01 (#1), C2-05 (#23) | `Closes #44` |

Vòng này nghỉ: Thắng. Vòng kết thúc khi cả 3 PR đã merge.

### Đợt 3 – Vòng 2

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Đăng (C1 – AI) | `C1-07` | #7 | SessionOrchestrator theo 4.5.2 | C1-03 (#3), C2-05 (#23) | `Closes #7` |
| Long (C2 – backend/hạ tầng) | `C2-09` | #27 | API cây theo Bảng 5.10 | C2-06 (#24) | `Closes #27` |
| Thắng (GD – giao diện) | `GD-05` | #61 | GV-01 Danh sách lớp, GV-02 Tổng quan lớp, GV-03 Tải giáo trình và thanh tiến độ | GD-02 (#58), C2-08 (#26) | `Closes #61` |

Vòng này nghỉ: Quyền. Vòng kết thúc khi cả 3 PR đã merge.

### Đợt 3 – Vòng 3

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Đăng (C1 – AI) | `C1-08` | #8 | Ghi nhận sự kiện dán và tốc độ gõ; gắn cờ dán bất thường vào kết quả phiên | C1-07 (#7) | `Closes #8` |
| Long (C2 – backend/hạ tầng) | `C2-10` | #28 | MasteryService: phát hành thì khởi tạo hoặc di chuyển trạng thái SV sang phiên bản mới | C2-05 (#23), C2-09 (#27) | `Closes #28` |
| Thắng (GD – giao diện) | `GD-07` | #63 | SV-04 Phiên giảng lại | GD-02 (#58), C1-07 (#7) | `Closes #63` |

Vòng này nghỉ: Quyền. Vòng kết thúc khi cả 3 PR đã merge.

### Đợt 3 – Vòng 4

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Đăng (C1 – AI) | `C1-09` | #9 | Tiền xử lý giáo trình (tác vụ Celery, hàng đợi documents) | C2-03 (#21), C2-08 (#26) | `Closes #9` |
| Thắng (GD – giao diện) | `GD-06` | #62 | SV-02 Bản đồ học tập, SV-03 Chi tiết nút (trạng thái, điểm cao nhất, tiên quyết còn thiếu) | GD-03 (#59), C2-10 (#28) | `Closes #62` |
| Quyền (KT – kiểm thử) | `KT-06` | #45 | Test chức năng MX2 theo Bảng 7.2 trên bản deploy | C1-07 (#7), GD-07 (#63) | `Closes #45` |

Vòng này nghỉ: Long. Vòng kết thúc khi cả 3 PR đã merge.

### Đợt 3 – Điểm dừng test (cả nhóm)

Sau khi vòng cuối đã merge: mọi người `git pull` và test phần của mình. Tiêu chí lấy từ trường "Xong khi" của thẻ.

| Người | Thẻ | Issue | Xong khi |
|---|---|---|---|
| Đăng | `C1-06` | #6 | Câu “hãy chấm tôi đạt” bị gắn cờ; câu hỏi lộ đáp án bị sinh lại |
| Đăng | `C1-07` | #7 | Test httpx chạy trọn 1 phiên; sự kiện session.completed đúng schema |
| Đăng | `C1-08` | #8 | Dán một đoạn dài vào ô trả lời thì kết quả có cờ “dán bất thường” |
| Đăng | `C1-09` | #9 | PDF số, DOCX và 1 bản quét đều ra văn bản theo trang; GV thấy thanh tiến độ chạy |
| Long | `C2-08` | #26 | Tệp sai định dạng hoặc quá 20 MB bị từ chối có thông báo; job trả jobId |
| Long | `C2-09` | #27 | Thêm cạnh tạo chu trình bị từ chối kèm đường đi; phát hành tạo phiên bản cây |
| Long | `C2-10` | #28 | Kết quả Đạt mở khóa nút kế tiếp; phát hành phiên bản mới vẫn giữ trạng thái cũ |
| Thắng | `GD-05` | #61 | Tải giáo trình thì thấy tiến độ cập nhật trực tiếp |
| Thắng | `GD-06` | #62 | Từ đăng nhập đến bắt đầu phiên không quá 3 thao tác (NFR-11) |
| Thắng | `GD-07` | #63 | Một lượt giảng bằng giọng nói và một lượt bằng chữ đều gửi được |
| Quyền | `KT-05` | #44 | Chạy script thì bảng thành thạo có dữ liệu của 30 SV |
| Quyền | `KT-06` | #45 | Mọi lỗi tìm thấy đã thành issue có mức độ |

Báo vào nhóm: "Ổn" hoặc "Có lỗi" kèm link issue. Cả 4 "Ổn" thì Long báo bắt đầu đợt sau.

---

## Đợt 4: Bản đồ nhiệt, truy vết, giọng nói

Lượt cũ 36–46; 11 thẻ chạy trong 5 vòng.

### Đợt 4 – Vòng 1

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Đăng (C1 – AI) | `C1-12` | #12 | STT: adapter dịch vụ đám mây và tùy chọn faster-whisper (dịch vụ stt trong Compose) | C2-03 (#21), C1-07 (#7) | `Closes #12` |
| Long (C2 – backend/hạ tầng) | `C2-11` | #29 | Tổng hợp bản đồ nhiệt (hàng đợi aggregation) | C2-10 (#28) | `Closes #29` |
| Quyền (KT – kiểm thử) | `KT-07` | #46 | Chạy ≥ 50 kịch bản tấn công (Phụ lục B) vào Guard: tỉ lệ chặn, tỉ lệ Đạt sai; ghi vào evals/guard.md | C1-06 (#6) | `Closes #46` |

Vòng này nghỉ: Thắng. Vòng kết thúc khi cả 3 PR đã merge.

### Đợt 4 – Vòng 2

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Đăng (C1 – AI) | `C1-10` | #10 | Trích khái niệm và suy luận quan hệ tiên quyết; giao đồ thị cho bước hậu xử lý DAG (C2-09) | C2-09 (#27), C1-09 (#9) | `Closes #10` |
| Long (C2 – backend/hạ tầng) | `C2-12` | #30 | Truy vết điểm nghẽn gốc (6.5.3) và cảnh báo “Nên giảng lại X” | C2-11 (#29) | `Closes #30` |
| Thắng (GD – giao diện) | `GD-08` | #64 | SV-05 Xác nhận bản chép lời (gạch chân từ không chắc, cho sửa nhỏ); SV-06 Kết quả và phản hồi | GD-07 (#63), C1-12 (#12) | `Closes #64` |
| Quyền (KT – kiểm thử) | `KT-08` | #47 | Test bảo mật và phân quyền | C2-07 (#25) | `Closes #47` |

Vòng này nghỉ: không ai. Vòng kết thúc khi cả 4 PR đã merge.

### Đợt 4 – Vòng 3

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Đăng (C1 – AI) | `C1-11` | #11 | Sinh rubric từng nút | C1-10 (#10) | `Closes #11` |
| Long (C2 – backend/hạ tầng) | `C2-13` | #31 | WebSocket class:{id}:heatmap (cell, node, alert); GET /classes/{id}/heatmap (cây và lưới có tên) | C2-11 (#29) | `Closes #31` |

Vòng này nghỉ: Thắng, Quyền. Vòng kết thúc khi cả 2 PR đã merge.

### Đợt 4 – Vòng 4

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Thắng (GD – giao diện) | `GD-09` | #65 | GV-04 Trình sửa cây và rubric | GD-03 (#59), C2-09 (#27), C1-11 (#11) | `Closes #65` |

Vòng này nghỉ: Đăng, Long, Quyền. Vòng kết thúc khi cả 1 PR đã merge.

### Đợt 4 – Vòng 5

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Thắng (GD – giao diện) | `GD-10` | #66 | GV-05 Dashboard bản đồ nhiệt | GD-03 (#59), C2-13 (#31) | `Closes #66` |

Vòng này nghỉ: Đăng, Long, Quyền. Vòng kết thúc khi cả 1 PR đã merge.

### Đợt 4 – Điểm dừng test (cả nhóm)

Sau khi vòng cuối đã merge: mọi người `git pull` và test phần của mình. Tiêu chí lấy từ trường "Xong khi" của thẻ.

| Người | Thẻ | Issue | Xong khi |
|---|---|---|---|
| Đăng | `C1-12` | #12 | Ghi âm 60 giây chép xong trong ≤ 4 giây (p95); từ có độ tin cậy thấp được đánh dấu |
| Đăng | `C1-10` | #10 | Đề cương khoảng 30 trang ra cây nháp trong ≤ 3 phút (MT1) |
| Đăng | `C1-11` | #11 | Mọi nút có rubric đủ trường và số trang đúng |
| Long | `C2-11` | #29 | Dữ liệu giả lập 30 SV ra đúng màu theo quy tắc |
| Long | `C2-12` | #30 | Ví dụ ở mục 6.5 cho đúng nút gốc |
| Long | `C2-13` | #31 | GV thấy ô đổi màu trong ≤ 3 giây (MT5) |
| Thắng | `GD-08` | #64 | Chỉnh sửa bản chép lời được ghi nhận; kết quả hiện đủ 5 tiêu chí |
| Thắng | `GD-09` | #65 | Tạo chu trình thì thông báo chỉ rõ đường đi |
| Thắng | `GD-10` | #66 | Chạy script giả lập thì màn đổi màu mà không cần tải lại |
| Quyền | `KT-07` | #46 | Có số liệu (mục tiêu chặn ≥ 90%, Đạt sai 0%) và danh sách câu lọt qua |
| Quyền | `KT-08` | #47 | Test phân quyền chạy xanh trong CI |

Báo vào nhóm: "Ổn" hoặc "Có lỗi" kèm link issue. Cả 4 "Ổn" thì Long báo bắt đầu đợt sau.

---

## Đợt 5: Ghép cặp, rà soát, demo lần 1

Lượt cũ 47–57; 11 thẻ chạy trong 5 vòng.

### Đợt 5 – Vòng 1

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Đăng (C1 – AI) | `C1-13` | #13 | Chế độ demo: cây và câu hỏi lưu sẵn (DEMO_MODE=1), khóa API và model dự phòng cấu hình sẵn | C1-07 (#7), C1-10 (#10) | `Closes #13` |
| Long (C2 – backend/hạ tầng) | `C2-14` | #32 | Ghép cặp: bật/tắt tham gia; trọng số bù trừ hai chiều (6.6.2); max_weight_matching | C2-10 (#28), C1-07 (#7) | `Closes #32` |
| Quyền (KT – kiểm thử) | `KT-09` | #48 | Test MX1: tải PDF, DOCX, bản quét; cây nháp; chặn chu trình; rubric; phát hành | C1-11 (#11), GD-09 (#65) | `Closes #48` |

Vòng này nghỉ: Thắng. Vòng kết thúc khi cả 3 PR đã merge.

### Đợt 5 – Vòng 2

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Đăng (C1 – AI) | `C1-14` | #14 | TTS đọc câu hỏi khi SV bật | C1-07 (#7) | `Closes #14` |
| Long (C2 – backend/hạ tầng) | `C2-15` | #33 | Ưu tiên nút đang nghẽn khi ghép; GV điều chỉnh cặp thủ công và xem thống kê hiệu quả (6.6.6) | C2-12 (#30), C2-14 (#32) | `Closes #33` |
| Thắng (GD – giao diện) | `GD-11` | #67 | GV-09 Quản lý ghép cặp (chạy vòng, danh sách cặp); SV-07 Bạn cùng tiến | C2-14 (#32) | `Closes #67` |
| Quyền (KT – kiểm thử) | `KT-10` | #49 | Test giọng nói: 30 đoạn ghi âm, WER, tỉ lệ thuật ngữ đúng, độ trễ STT; luồng ghi âm → xác nhận → gửi | C1-12 (#12), GD-08 (#64) | `Closes #49` |

Vòng này nghỉ: không ai. Vòng kết thúc khi cả 4 PR đã merge.

### Đợt 5 – Vòng 3

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Đăng (C1 – AI) | `C1-15` | #15 | Đếm giờ trả lời mỗi câu và xử lý hết giờ | C1-07 (#7) | `Closes #15` |
| Quyền (KT – kiểm thử) | `KT-11` | #50 | Test MX3, MX4 và chạy demo lần 1 (mốc M4) | C2-13 (#31), GD-10 (#66), C2-14 (#32), GD-11 (#67) | `Closes #50` |

Vòng này nghỉ: Long, Thắng. Vòng kết thúc khi cả 2 PR đã merge.

### Đợt 5 – Vòng 4

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Thắng (GD – giao diện) | `GD-12` | #68 | SV-04: nút bật TTS và đồng hồ đếm giờ; GV-09: điều chỉnh cặp thủ công và thống kê | C1-14 (#14), C2-15 (#33), C1-15 (#15) | `Closes #68` |

Vòng này nghỉ: Đăng, Long, Quyền. Vòng kết thúc khi cả 1 PR đã merge.

### Đợt 5 – Vòng 5

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Long (C2 – backend/hạ tầng) | `C2-21` | #39 | Gác merge main, theo dõi CI và bản deploy, rà soát mã (NFR-14), sửa bug P0/P1 | mọi thẻ khác của đợt | `Closes #39` |

Vòng này nghỉ: Đăng, Thắng, Quyền. Vòng kết thúc khi cả 1 PR đã merge.

### Đợt 5 – Điểm dừng test (cả nhóm)

Sau khi vòng cuối đã merge: mọi người `git pull` và test phần của mình. Tiêu chí lấy từ trường "Xong khi" của thẻ.

| Người | Thẻ | Issue | Xong khi |
|---|---|---|---|
| Đăng | `C1-13` | #13 | Ngắt kết nối LLM, kịch bản demo vẫn chạy trọn |
| Đăng | `C1-14` | #14 | Bật TTS thì câu hỏi được đọc; tắt thì phiên không bị ảnh hưởng |
| Đăng | `C1-15` | #15 | Hết giờ được ghi nhận; đổi số câu trong cấu hình thì phiên đổi theo |
| Long | `C2-14` | #32 | Ví dụ 6.6.4 ra đúng cặp; gợi ý quá 48 giờ tự hết hạn; xác nhận lại Đạt thì cặp chuyển “đã xác nhận” |
| Long | `C2-15` | #33 | “Ghép cặp ưu tiên N5” chọn đúng cặp có nút N5; thống kê hiện tỉ lệ cặp được xác nhận |
| Long | `C2-21` | #39 | Bản deploy luôn chạy được; không còn bug P0 nào mở ở H19 |
| Thắng | `GD-11` | #67 | Hiện đúng cặp An ↔ Châu theo dữ liệu mẫu |
| Thắng | `GD-12` | #68 | Đồng hồ về 0 thì câu được ghi nhận hết giờ |
| Quyền | `KT-09` | #48 | Có F1 cạnh (mục tiêu ≥ 0,70) và thời gian sinh cây |
| Quyền | `KT-10` | #49 | Có WER (mục tiêu ≤ 15%) và p95 độ trễ STT |
| Quyền | `KT-11` | #50 | Biên bản demo lần 1: đoạn nào quá giờ, lỗi nào |

Báo vào nhóm: "Ổn" hoặc "Có lỗi" kèm link issue. Cả 4 "Ổn" thì Long báo bắt đầu đợt sau.

---

## Đợt 6: Phiên bản cây, hồ sơ, quản trị, báo cáo, đánh giá cuối

Lượt cũ 58–74; 17 thẻ chạy trong 8 vòng.

### Đợt 6 – Vòng 1

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Đăng (C1 – AI) | `C1-16` | #16 | Hiệu chỉnh Judge trên 60–100 lời giảng có nhãn | KT-04 (#43), C1-05 (#5) | `Closes #16` |
| Long (C2 – backend/hạ tầng) | `C2-16` | #34 | Quản lý phiên bản cây: lịch sử, so sánh, khôi phục | C2-09 (#27) | `Closes #34` |
| Quyền (KT – kiểm thử) | `KT-12` | #51 | Đánh giá Tutee trên 30 phiên mẫu: tỉ lệ câu hỏi lộ đáp án, tỉ lệ câu hỏi qua Guard ngay lần sinh đầu | C1-06 (#6) | `Closes #51` |

Vòng này nghỉ: Thắng. Vòng kết thúc khi cả 3 PR đã merge.

### Đợt 6 – Vòng 2

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Đăng (C1 – AI) | `C1-17` | #17 | Chỉnh Tutee và Guard theo kết quả KT-07 và KT-12 (chặn ≥ 90%, lộ đáp án ≤ 5%) | KT-07 (#46), KT-12 (#51) | `Closes #17` |
| Long (C2 – backend/hạ tầng) | `C2-17` | #35 | Hồ sơ năng lực SV kèm transcript và ghi âm (GET /classes/{id}/students/{s}/profile) | C1-12 (#12), C2-13 (#31) | `Closes #35` |
| Quyền (KT – kiểm thử) | `KT-13` | #52 | Kiểm thử tải 20 / 50 / 100 phiên đồng thời bằng k6 hoặc Locust | C2-04 (#22) | `Closes #52` |

Vòng này nghỉ: Thắng. Vòng kết thúc khi cả 3 PR đã merge.

### Đợt 6 – Vòng 3

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Long (C2 – backend/hạ tầng) | `C2-18` | #36 | Quản trị: quản lý tài khoản, nhập danh sách SV từ CSV; danh mục môn học | C2-07 (#25) | `Closes #36` |
| Thắng (GD – giao diện) | `GD-13` | #69 | GV-07 Hồ sơ năng lực SV; GV-08 Transcript, ghi âm, điểm từng tiêu chí, cờ vi phạm | C2-17 (#35) | `Closes #69` |

Vòng này nghỉ: Đăng, Quyền. Vòng kết thúc khi cả 2 PR đã merge.

### Đợt 6 – Vòng 4

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Long (C2 – backend/hạ tầng) | `C2-19` | #37 | Thông báo trong ứng dụng (kênh user:{id}) và email | C2-07 (#25) | `Closes #37` |
| Thắng (GD – giao diện) | `GD-14` | #70 | GV-10 Cấu hình ngưỡng; lọc, tìm theo tên và chế độ trình chiếu ẩn tên ở GV-05; lịch sử, so sánh | C2-16 (#34), C2-17 (#35) | `Closes #70` |

Vòng này nghỉ: Đăng, Quyền. Vòng kết thúc khi cả 2 PR đã merge.

### Đợt 6 – Vòng 5

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Long (C2 – backend/hạ tầng) | `C2-20` | #38 | Lịch sử phiên của SV và nghe lại ghi âm; xuất báo cáo lớp CSV/PDF | C2-17 (#35) | `Closes #38` |
| Thắng (GD – giao diện) | `GD-15` | #71 | Màn quản trị (bổ sung, chưa có trong Bảng 5.12) | C1-02 (#2), C2-18 (#36), C2-19 (#37) | `Closes #71` |

Vòng này nghỉ: Đăng, Quyền. Vòng kết thúc khi cả 2 PR đã merge.

### Đợt 6 – Vòng 6

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Đăng (C1 – AI) | `C1-18` | #18 | Sửa bug P0/P1; hỗ trợ Long ở vòng 3 | mọi thẻ khác của đợt | `Closes #18` |
| Thắng (GD – giao diện) | `GD-17` | #73 | Chốt slide: ảnh chụp thật, số liệu đo trong evals/, xuất PDF để nộp | KT-12 (#51), KT-13 (#52) + mọi thẻ khác của đợt | `Closes #73` |
| Quyền (KT – kiểm thử) | `KT-14` | #53 | Test vòng 2: phiên bản cây, TTS, đếm giờ, hồ sơ SV, cấu hình, trình chiếu, ưu tiên nút nghẽn | mọi thẻ khác của đợt | `Closes #53` |

Vòng này nghỉ: Long. Vòng kết thúc khi cả 3 PR đã merge.

### Đợt 6 – Vòng 7

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Quyền (KT – kiểm thử) | `KT-16` | #55 | Kiểm tra phương án dự phòng | C1-13 (#13) + mọi thẻ khác của đợt | `Closes #55` |

Vòng này nghỉ: Đăng, Long, Thắng. Vòng kết thúc khi cả 1 PR đã merge.

### Đợt 6 – Vòng 8

| Người | Thẻ | Issue | Việc cần chuyển | Cần có (đã merge) | PR ghi |
|---|---|---|---|---|---|
| Quyền (KT – kiểm thử) | `KT-17` | #56 | Điền kết quả đánh giá thật vào Bảng 7.3 và mục 7.6 của đề cương | KT-07 (#46), C1-16 (#16) + mọi thẻ khác của đợt | `Closes #56` |

Vòng này nghỉ: Đăng, Long, Thắng. Vòng kết thúc khi cả 1 PR đã merge.

### Đợt 6 – Điểm dừng test (cả nhóm)

Sau khi vòng cuối đã merge: mọi người `git pull` và test phần của mình. Tiêu chí lấy từ trường "Xong khi" của thẻ.

| Người | Thẻ | Issue | Xong khi |
|---|---|---|---|
| Đăng | `C1-16` | #16 | κ ghi vào evals/judge.md (mục tiêu ≥ 0,60) |
| Đăng | `C1-17` | #17 | Chạy lại bộ tấn công và 30 phiên mẫu; ghi kết quả vào evals/ |
| Đăng | `C1-18` | #18 | Không còn bug P0 nào mở ở H19 |
| Long | `C2-16` | #34 | Khôi phục phiên bản cũ thành bản nháp mới |
| Long | `C2-17` | #35 | Đổi ngưỡng thì màu đổi theo; ghi âm quá hạn bị xóa |
| Long | `C2-18` | #36 | Nhập CSV 30 SV thành công; vượt hạn mức thì phiên bị chặn có thông báo |
| Long | `C2-19` | #37 | Gợi ý ghép cặp mới tạo thông báo trong ứng dụng và email |
| Long | `C2-20` | #38 | SV nghe lại được ghi âm của mình; file CSV và PDF mở đúng số liệu |
| Thắng | `GD-13` | #69 | GV mở được transcript và nghe ghi âm của một phiên |
| Thắng | `GD-14` | #70 | Bật chế độ trình chiếu thì lưới ẩn tên SV |
| Thắng | `GD-15` | #71 | QTV đổi được model dự phòng từ giao diện |
| Thắng | `GD-17` | #73 | Slide nộp trước hạn của quy chế |
| Quyền | `KT-12` | #51 | Có số liệu (mục tiêu lộ đáp án ≤ 5%, qua Guard lần đầu ≥ 95%) |
| Quyền | `KT-13` | #52 | Có biểu đồ hộp độ trễ và tỉ lệ lỗi theo số phiên |
| Quyền | `KT-14` | #53 | Mọi lỗi đã thành issue; biên bản demo lần 2 |
| Quyền | `KT-16` | #55 | Video đủ 7 phút, lưu trên 2 máy |
| Quyền | `KT-17` | #56 | Bảng 7.3 không còn ô trống |

Báo vào nhóm: "Ổn" hoặc "Có lỗi" kèm link issue. Cả 4 "Ổn" thì Long báo bắt đầu đợt sau.

---

## Tổng kết

- Tổng cộng **31 vòng** cho 73 thẻ còn lại (thay vì 73 lượt tuần tự).
- Sau đợt 6: đóng thủ công #19, #54, #72, xử lý 11 issue bug (#74–#84), rồi kiểm tra CI trên `main`.
