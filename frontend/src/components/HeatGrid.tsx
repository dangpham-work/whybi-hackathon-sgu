/**
 * HeatGrid – lưới SV × Nút có tên và MSSV (FR-HM-02), ô đổi màu realtime qua kênh class:{id}:heatmap,
 * chế độ trình chiếu ẩn tên (FR-HM-09). Thẻ: GD-10, GD-14 (Thắng).
 */
export function HeatGrid({ hideNames = false }: { hideNames?: boolean }) {
  // TODO(GD-10): bảng dính cột tên; ô dùng MASTERY từ lib/status.ts (màu + biểu tượng)
  return <div className="text-ink-500">HeatGrid {hideNames ? "(ẩn tên)" : ""} – thẻ GD-10</div>;
}
