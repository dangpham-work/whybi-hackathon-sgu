# docs/status/thang.md   (chỉ Thắng sửa)

> Cập nhật sau mỗi thẻ (kế hoạch §4.2). Mọi người – và mọi phiên AI – đọc hết `docs/status/` trước khi sửa code.

- Xong:
  - GD-01 – khung giao diện 3 vai (PR #79)
  - GD-03 – component `SkillTree` (React Flow + dagre), dùng chung cho GV-04, GV-05, SV-02
- Phát sự kiện / hợp đồng đã chốt:
  - `SkillTree` (`frontend/src/components/SkillTree.tsx`): props `mode` (`edit` | `heatmap` | `learner`), `nodes` / `edges` (kiểu `Node` / `Edge` sinh từ OpenAPI), `mastery` / `heat` theo `key` của nút, `details`, `rootCauseKey`, `selectedKey`, `onNodeClick`, `onNodeMove`, `onConnect`.
  - Tự sắp xếp bằng `layoutTree()` (`frontend/src/lib/tree-layout.ts`, dùng dagre). Nếu mọi nút đã có `positionX/Y` thì dùng vị trí đã lưu.
  - `frontend/src/lib/api-types.ts` sinh lại từ OpenAPI của backend hiện tại.
- Đang làm: —
- Cần từ người khác:
  - Long (C2-02): giữ `Node.positionX/positionY` và `Edge.source` như `schemas/tree.py` hiện tại; SkillTree dựa vào các trường này.
  - Long (C2-13): bản đồ nhiệt nên trả màu theo `key` của nút (hoặc kèm `key`) để truyền thẳng vào `heat`.
