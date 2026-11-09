import { Link } from "react-router";
import type { Schema } from "../lib/api";
import { HEAT, MASTERY, type HeatColor, type MasteryState } from "../lib/status";

type Row = Schema<"GridRow">;
type Stat = Schema<"NodeStat">;

/**
 * HeatGrid – Ma trận thành thạo SV × Nút dạng bảng tính cố định hai chiều (FR-HM-02).
 * - Cố định thanh tiêu đề trên cùng (mã nút) khi cuộn dọc.
 * - Cố định cột sinh viên (tên + MSSV) khi cuộn ngang.
 * - Ô góc trên cùng bên trái cố định hai chiều như Excel freeze panes.
 * - Khung bảng có thanh cuộn riêng biệt, không làm cuộn cả trang web.
 * - `hideNames` = chế độ trình chiếu (FR-HM-09).
 */
export function HeatGrid({
  rows,
  nodes,
  classId,
  hideNames = false,
}: {
  rows: Row[];
  nodes: Stat[];
  classId?: string;
  hideNames?: boolean;
}) {
  if (rows.length === 0)
    return (
      <p className="rounded-lg border border-dashed border-line-strong p-4 text-body-m text-ink-500">
        Lớp chưa có sinh viên nào.
      </p>
    );

  return (
    <div className="relative w-full overflow-auto rounded-lg border border-line-soft bg-surface max-h-[calc(100vh-250px)] min-h-[500px] shadow-sm">
      <table aria-label="Lưới sinh viên theo nút" className="min-w-full border-separate border-spacing-0 text-body-s">
        <thead>
          <tr className="bg-app">
            <th
              scope="col"
              className="sticky top-0 left-0 z-30 bg-app px-4 py-3 text-left font-bold text-ink-900 border-b-2 border-r-2 border-line-strong shadow-[2px_2px_4px_rgba(0,0,0,0.06)] min-w-[220px]"
            >
              Sinh viên ({rows.length})
            </th>
            {nodes.map((n) => (
              <th
                key={n.nodeId}
                scope="col"
                title={`${n.code} – ${n.title}`}
                className="sticky top-0 z-20 bg-app px-3 py-2 text-center font-bold text-ink-900 border-b-2 border-r border-line-soft shadow-[0_2px_4px_rgba(0,0,0,0.06)] min-w-[76px]"
              >
                <span className="block">{n.code}</span>
                <span
                  className={`inline-block mt-0.5 rounded-full px-1.5 py-0.5 text-[10px] font-semibold border ${
                    HEAT[n.color as HeatColor]?.className || ""
                  }`}
                >
                  {n.passRate != null ? `${Math.round(n.passRate * 100)}%` : "–"}
                </span>
              </th>
            ))}
            <th
              scope="col"
              className="sticky top-0 right-0 z-20 bg-app px-3 py-2 text-center font-bold text-ink-900 border-b-2 border-l-2 border-line-strong shadow-[-2px_0_4px_rgba(0,0,0,0.06)] min-w-[85px]"
            >
              Tiến độ
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.studentId} className="hover:bg-teal-soft/15 transition-colors group">
              <th
                scope="row"
                className="sticky left-0 z-10 whitespace-nowrap bg-surface px-4 py-2 text-left font-normal border-b border-r-2 border-line-strong shadow-[2px_0_4px_rgba(0,0,0,0.06)] group-hover:bg-teal-soft/20 transition-colors"
              >
                {hideNames ? (
                  <span className="font-semibold text-ink-900">SV {String(i + 1).padStart(2, "0")}</span>
                ) : classId ? (
                  <Link
                    to={`/gv/classes/${classId}/students/${r.studentId}`}
                    title={`Xem hồ sơ năng lực của ${r.studentName}`}
                    className="inline-flex items-baseline gap-1.5 hover:text-teal hover:underline"
                  >
                    <span className="font-semibold text-ink-900">{r.studentName}</span>
                    <span className="text-body-xs text-ink-400 font-mono">{r.studentCode}</span>
                  </Link>
                ) : (
                  <span className="inline-flex items-baseline gap-1.5">
                    <span className="font-semibold text-ink-900">{r.studentName}</span>
                    <span className="text-body-xs text-ink-400 font-mono">{r.studentCode}</span>
                  </span>
                )}
              </th>
              {nodes.map((n) => (
                <td key={n.nodeId} className="px-1 py-1.5 text-center border-b border-r border-line-soft/60">
                  <Cell state={(n.nodeKey && r.statesByKey?.[n.nodeKey]) as MasteryState | undefined} />
                </td>
              ))}
              <td className="sticky right-0 z-10 whitespace-nowrap bg-surface px-3 py-1.5 text-center font-semibold text-body-xs border-b border-l-2 border-line-strong shadow-[-2px_0_4px_rgba(0,0,0,0.06)] group-hover:bg-teal-soft/20">
                {r.progress != null ? `${Math.round(r.progress * 100)}%` : `${r.masteredCount ?? 0} nút`}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="bg-app font-semibold">
            <th
              scope="row"
              className="sticky bottom-0 left-0 z-30 bg-app px-4 py-2.5 text-left border-t-2 border-r-2 border-line-strong shadow-[2px_-2px_4px_rgba(0,0,0,0.06)]"
            >
              Tỉ lệ Đạt của lớp
            </th>
            {nodes.map((n) => (
              <td
                key={n.nodeId}
                className="sticky bottom-0 z-20 bg-app px-2 py-2 text-center text-body-xs font-bold border-t-2 border-r border-line-soft shadow-[0_-2px_4px_rgba(0,0,0,0.06)]"
              >
                {n.passRate != null ? `${Math.round(n.passRate * 100)}%` : "–"}
              </td>
            ))}
            <td className="sticky bottom-0 right-0 z-30 bg-app px-2 py-2 text-center text-body-xs font-bold border-t-2 border-l-2 border-line-strong shadow-[-2px_-2px_4px_rgba(0,0,0,0.06)]">
              {rows.length} SV
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function Cell({ state }: { state?: MasteryState }) {
  if (!state) return <span className="text-ink-300" aria-label="Chưa có dữ liệu">–</span>;
  const look = MASTERY[state];
  const Icon = look.icon;
  return (
    <span
      title={look.label}
      aria-label={look.label}
      className={`inline-flex size-7 items-center justify-center rounded-md border ${look.className}`}
    >
      <Icon aria-hidden size={14} strokeWidth={2.5} />
    </span>
  );
}
