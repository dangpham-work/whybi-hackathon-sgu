<!-- Suy luận quan hệ tiên quyết (C1-10) · mục 6.1.3 · chủ: Đăng · phiên bản: v1 -->
<!-- Biến {ngoặc nhọn} được điền lúc chạy. Nhiệt độ 0. -->

Khái niệm đích B: "{target_title}" – {target_description}
Với MỖI khái niệm ứng viên A dưới đây, trả lời: để hiểu B, sinh viên có BẮT BUỘC phải hiểu A trước không?
{candidates}
QUY TẮC:
- Chỉ trả is_prerequisite = true khi thiếu A thì không thể hiểu B (không phải chỉ "liên quan" hay "cùng chương").
- `confidence` ∈ [0, 1] là độ chắc chắn của bạn; `reason` một câu ngắn.
- Trả đủ một mục cho mỗi ứng viên, dùng đúng `from_key`.
Trả về JSON: {"items": [{"from_key": "...", "is_prerequisite": true, "confidence": 0.8, "reason": "..."}]}
