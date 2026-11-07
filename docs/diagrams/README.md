# Sơ đồ PlantUML (Phụ lục E của đề cương v0.1)

Mỗi tệp tương ứng một hình trong đề cương. Xuất lại: `plantuml -tpng docs/diagrams/*.puml`
(các tệp có `!include common.iuml` cần chạy trong thư mục này).

Ảnh PNG xuất sẵn (từ bản Word của đề cương) nằm trong [`png/`](png/), cùng tên với tệp `.puml`; xuất lại thì ghi đè: `plantuml -tpng -o png *.puml`.

| Tệp | Hình |
|---|---|
| [01_h1_1.puml](01_h1_1.puml) | Hình 1.1. Vòng lặp “hiểu lướt” hiện nay và vòng lặp “hiểu thật” đề xuất |
| [02_h1_2.puml](02_h1_2.puml) | Hình 1.2. Cây vấn đề (Problem Tree): nguyên nhân gốc – vấn đề cốt lõi – hệ quả |
| [03_h1_3.puml](03_h1_3.puml) | Hình 1.3. Chu trình 4 mắt xích khép kín (có bước xác nhận lại sau khi học cặp) |
| [04_h2_1.puml](04_h2_1.puml) | Hình 2.1. Ánh xạ cơ sở sư phạm vào các mắt xích của hệ thống |
| [05_h2_2.puml](05_h2_2.puml) | Hình 2.2. Ví dụ đồ thị tiên quyết (DAG) cho môn Cấu trúc dữ liệu và Giải thuật |
| [06_h2_3.puml](06_h2_3.puml) | Hình 2.3. Kiến trúc RAG tổng quát và cách áp dụng trong hệ thống |
| [07_h2_4.puml](07_h2_4.puml) | Hình 2.4. Định vị giải pháp theo hai trục: vai trò người dạy và phạm vi phục vụ |
| [08_h3_1.puml](08_h3_1.puml) | Hình 3.1. Sơ đồ ngữ cảnh hệ thống (Context Diagram) |
| [09_h3_2.puml](09_h3_2.puml) | Hình 3.2. Sơ đồ phân rã chức năng (BFD) |
| [10_act_overall_a.puml](10_act_overall_a.puml) | Hình 4.1. Biểu đồ hoạt động tổng thể (a) – thiết lập môn học |
| [11_act_overall_b.puml](11_act_overall_b.puml) | Hình 4.2. Biểu đồ hoạt động tổng thể (b) – vòng lặp học tập |
| [12_uc_overall.puml](12_uc_overall.puml) | Hình 4.3. Biểu đồ Use Case tổng quát |
| [13_uc_tree.puml](13_uc_tree.puml) | Hình 4.4. Use Case phân rã – Quản lý môn học và cây kỹ năng |
| [14_uc_teach.puml](14_uc_teach.puml) | Hình 4.5. Use Case phân rã – Giảng lại cho AI |
| [15_uc_heatmap.puml](15_uc_heatmap.puml) | Hình 4.6. Use Case phân rã – Theo dõi lớp học (bản đồ nhiệt) |
| [16_uc_peer.puml](16_uc_peer.puml) | Hình 4.7. Use Case phân rã – Ghép cặp bạn cùng tiến |
| [17_uc_admin.puml](17_uc_admin.puml) | Hình 4.8. Use Case phân rã – Quản trị hệ thống và chức năng chung |
| [18_act_tree_a.puml](18_act_tree_a.puml) | Hình 4.9. Biểu đồ hoạt động – Sinh cây kỹ năng tự động (a) |
| [19_act_tree_b.puml](19_act_tree_b.puml) | Hình 4.10. Biểu đồ hoạt động – Duyệt và phát hành cây kỹ năng (b) |
| [20_act_teach_a.puml](20_act_teach_a.puml) | Hình 4.11. Biểu đồ hoạt động – Phiên giảng lại (a): khởi tạo và giảng giải bằng giọng nói / văn bản |
| [21_act_teach_b.puml](21_act_teach_b.puml) | Hình 4.12. Biểu đồ hoạt động – Phiên giảng lại (b): phản biện và chấm điểm |
| [22_act_heatmap.puml](22_act_heatmap.puml) | Hình 4.13. Biểu đồ hoạt động – Tổng hợp bản đồ nhiệt và cảnh báo điểm nghẽn |
| [23_act_peer.puml](23_act_peer.puml) | Hình 4.14. Biểu đồ hoạt động – Ghép cặp bạn cùng tiến và xác nhận lại |
| [24_seq_tree_upload.puml](24_seq_tree_upload.puml) | Hình 4.15. Biểu đồ tuần tự – Tải giáo trình lên (UC05) |
| [25_seq_tree_extract.puml](25_seq_tree_extract.puml) | Hình 4.16. Biểu đồ tuần tự – Xử lý nền trích xuất và sinh cây kỹ năng (UC06) |
| [26_seq_tree_publish.puml](26_seq_tree_publish.puml) | Hình 4.17. Biểu đồ tuần tự – Chỉnh sửa, duyệt và phát hành cây (UC07–UC09) |
| [27_seq_teach_init.puml](27_seq_teach_init.puml) | Hình 4.18. Biểu đồ tuần tự – Phiên giảng lại (1/4): khởi tạo phiên |
| [28_seq_teach_input.puml](28_seq_teach_input.puml) | Hình 4.19. Biểu đồ tuần tự – Phiên giảng lại (2/4): giảng giải bằng giọng nói hoặc văn bản |
| [29_seq_teach_challenge.puml](29_seq_teach_challenge.puml) | Hình 4.20. Biểu đồ tuần tự – Phiên giảng lại (3/4): vòng phản biện Socratic |
| [30_seq_teach_eval.puml](30_seq_teach_eval.puml) | Hình 4.21. Biểu đồ tuần tự – Phiên giảng lại (4/4): chấm điểm và cập nhật thành thạo |
| [31_seq_heatmap.puml](31_seq_heatmap.puml) | Hình 4.22. Biểu đồ tuần tự – Cập nhật bản đồ nhiệt thời gian thực và xem chi tiết nút |
| [32_seq_peer_round.puml](32_seq_peer_round.puml) | Hình 4.23. Biểu đồ tuần tự – Chạy vòng ghép cặp (UC15) |
| [33_seq_peer_verify.puml](33_seq_peer_verify.puml) | Hình 4.24. Biểu đồ tuần tự – Phản hồi gợi ý và xác nhận lại (UC22–UC23) |
| [34_st_mastery.puml](34_st_mastery.puml) | Hình 4.25. Biểu đồ trạng thái – MasteryRecord |
| [35_st_session.puml](35_st_session.puml) | Hình 4.26. Biểu đồ trạng thái – TeachingSession (mức tổng quát) |
| [36_st_session_explain.puml](36_st_session_explain.puml) | Hình 4.27. Trạng thái con của ĐANG GIẢNG GIẢI (giọng nói / văn bản) |
| [37_st_session_challenge.puml](37_st_session_challenge.puml) | Hình 4.28. Trạng thái con của ĐANG PHẢN BIỆN |
| [38_st_tree.puml](38_st_tree.puml) | Hình 4.29. Biểu đồ trạng thái – TreeVersion |
| [39_st_match.puml](39_st_match.puml) | Hình 4.30. Biểu đồ trạng thái – PeerMatch |
| [40_cls_overview.puml](40_cls_overview.puml) | Hình 4.31. Biểu đồ lớp phân tích – tổng quan quan hệ giữa các lớp |
| [41_cls_users.puml](41_cls_users.puml) | Hình 4.32. Biểu đồ lớp phân tích (1) – Người dùng, lớp học và tài liệu |
| [42_cls_tree.puml](42_cls_tree.puml) | Hình 4.33. Biểu đồ lớp phân tích (2) – Cây kỹ năng và rubric |
| [43_cls_session.puml](43_cls_session.puml) | Hình 4.34. Biểu đồ lớp phân tích (3) – Phiên giảng lại, đánh giá và thành thạo |
| [44_cls_peer.puml](44_cls_peer.puml) | Hình 4.35. Biểu đồ lớp phân tích (4) – Bản đồ nhiệt và ghép cặp |
| [45_cls_enums.puml](45_cls_enums.puml) | Hình 4.36. Các kiểu liệt kê (enumeration) dùng trong mô hình |
| [46_cls_bce.puml](46_cls_bce.puml) | Hình 4.37. Biểu đồ lớp phân tích theo mẫu Boundary – Control – Entity cho UC19 |
| [47_arch_overview.puml](47_arch_overview.puml) | Hình 5.1. Kiến trúc tổng thể hệ thống (phân tầng) |
| [48_comp_ai.puml](48_comp_ai.puml) | Hình 5.2. Biểu đồ thành phần – tầng AI và các giao diện cung cấp / yêu cầu |
| [49_erd_overview.puml](49_erd_overview.puml) | Hình 5.3. Mô hình thực thể – liên kết (ERD) tổng quan – 30 bảng |
| [50_erd_users.puml](50_erd_users.puml) | Hình 5.4. ERD chi tiết (1) – Người dùng, lớp học, tài liệu và thông báo |
| [51_erd_tree.puml](51_erd_tree.puml) | Hình 5.5. ERD chi tiết (2) – Cây kỹ năng và rubric |
| [52_erd_session.puml](52_erd_session.puml) | Hình 5.6. ERD chi tiết (3) – Phiên giảng lại, đánh giá và thành thạo |
| [53_erd_peer.puml](53_erd_peer.puml) | Hình 5.7. ERD chi tiết (4) – Thống kê bản đồ nhiệt, ghép cặp, cấu hình và nhật ký |
| [54_matrix_illus.puml](54_matrix_illus.puml) | Hình 5.8. Ma trận thành thạo và cách 4 mắt xích đọc / ghi |
| [55_cls_design_ai.puml](55_cls_design_ai.puml) | Hình 5.9. Biểu đồ lớp thiết kế (1) – Adapter cho nhà cung cấp AI và dịch vụ giọng nói |
| [56_cls_design_agents.puml](56_cls_design_agents.puml) | Hình 5.10. Biểu đồ lớp thiết kế (2) – Các tác tử AI, chiến lược câu hỏi và chuỗi kiểm duyệt |
| [57_cls_design_domain.puml](57_cls_design_domain.puml) | Hình 5.11. Biểu đồ lớp thiết kế (3) – Thành thạo, sự kiện và bản đồ nhiệt |
| [58_cls_design_match.puml](58_cls_design_match.puml) | Hình 5.12. Biểu đồ lớp thiết kế (4) – Ghép cặp, cây kỹ năng và kho dữ liệu |
| [59_screen_flow.puml](59_screen_flow.puml) | Hình 5.13. Sơ đồ điều hướng màn hình (Screen Flow) |
| [60_wf_tree_editor.puml](60_wf_tree_editor.puml) | Hình 5.14. Wireframe GV-04 – Trình sửa cây kỹ năng và rubric |
| [61_wf_heatmap_tree.puml](61_wf_heatmap_tree.puml) | Hình 5.15. Wireframe GV-05a – Dashboard bản đồ nhiệt (chế độ cây) |
| [62_wf_heatmap_grid.puml](62_wf_heatmap_grid.puml) | Hình 5.16. Wireframe GV-05b – Dashboard bản đồ nhiệt (lưới SV × Nút, hiển thị tên) |
| [63_wf_node_detail.puml](63_wf_node_detail.puml) | Hình 5.17. Wireframe GV-06 – Chi tiết nút và điểm nghẽn |
| [64_wf_student_map.puml](64_wf_student_map.puml) | Hình 5.18. Wireframe SV-02 – Bản đồ học tập cá nhân |
| [65_wf_session.puml](65_wf_session.puml) | Hình 5.19. Wireframe SV-04 – Phiên giảng lại (giọng nói + văn bản) |
| [66_wf_transcript_confirm.puml](66_wf_transcript_confirm.puml) | Hình 5.20. Wireframe SV-05 – Xác nhận bản chép lời khi độ tin cậy STT thấp |
| [67_wf_result.puml](67_wf_result.puml) | Hình 5.21. Wireframe SV-06 – Kết quả và phản hồi sau phiên |
| [68_wf_peer.puml](68_wf_peer.puml) | Hình 5.22. Wireframe SV-07 – Gợi ý bạn cùng tiến |
| [69_legend_states.puml](69_legend_states.puml) | Hình 5.23. Quy ước màu, biểu tượng và ý nghĩa trạng thái |
| [70_sec_layers.puml](70_sec_layers.puml) | Hình 5.24. Các lớp phòng vệ chống gian lận và tấn công prompt trong phiên giảng lại |
| [71_deploy.puml](71_deploy.puml) | Hình 5.25. Biểu đồ triển khai (Deployment Diagram) |
| [72_ai_pipeline_tree.puml](72_ai_pipeline_tree.puml) | Hình 6.1. Pipeline trích xuất cây kỹ năng (a): tiền xử lý và trích xuất khái niệm |
| [73_ai_pipeline_tree_b.puml](73_ai_pipeline_tree_b.puml) | Hình 6.2. Pipeline trích xuất cây kỹ năng (b): suy luận tiên quyết, hậu xử lý và sinh rubric |
| [74_tree_postprocess.puml](74_tree_postprocess.puml) | Hình 6.3. Ví dụ hậu xử lý cây: gộp trùng, phá chu trình và rút gọn bắc cầu |
| [75_multi_agent.puml](75_multi_agent.puml) | Hình 6.4. Kiến trúc đa tác tử trong một phiên giảng lại |
| [76_prompt_structure.puml](76_prompt_structure.puml) | Hình 6.5. Cấu trúc prompt của tác tử Tutee cho mỗi lượt hỏi |
| [77_question_strategy.puml](77_question_strategy.puml) | Hình 6.6. Lưu đồ chọn câu hỏi phản biện tiếp theo |
| [78_scoring_flow.puml](78_scoring_flow.puml) | Hình 6.7. Luồng chấm điểm mức độ hiểu của Judge Agent |
| [79_voice_pipeline.puml](79_voice_pipeline.puml) | Hình 6.8. Pipeline xử lý giọng nói (STT) và đọc câu hỏi (TTS) |
| [80_heatmap_example.puml](80_heatmap_example.puml) | Hình 6.9. Ví dụ bản đồ nhiệt trên cây và truy vết điểm nghẽn gốc |
| [81_rootcause_algo.puml](81_rootcause_algo.puml) | Hình 6.10. Lưu đồ thuật toán truy vết điểm nghẽn gốc |
| [82_matching_example.puml](82_matching_example.puml) | Hình 6.11. Ví dụ ghép cặp bù trừ: ma trận năng lực → trọng số → kết quả |
| [83_matching_algo.puml](83_matching_algo.puml) | Hình 6.12. Lưu đồ thuật toán ghép cặp bù trừ |
| [84_eval_method.puml](84_eval_method.puml) | Hình 7.1. Quy trình đánh giá các thành phần AI |
| [85_demo_flow.puml](85_demo_flow.puml) | Hình 7.2. Kịch bản demo trước ban giám khảo (khoảng 7 phút) |
| [86_roadmap.puml](86_roadmap.puml) | Hình 8.1. Lộ trình phát triển sau Hackathon |
| [87_gantt_plan.puml](87_gantt_plan.puml) | Hình C.1. Kế hoạch thực hiện (Gantt, tính theo ngày làm việc tương đối) |
