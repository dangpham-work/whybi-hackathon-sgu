import type { Schema } from "../lib/api";
import { MASTERY, type MasteryState } from "../lib/status";

type Row = Schema<"GridRow">;
type Stat = Schema<"NodeStat">;

/**
 * HeatGrid – lưới SV × Nút có tên và MSSV (FR-HM-02). Ô tô màu theo trạng thái thành thạo kèm biểu tượng + chữ (NFR-12).
 * `hideNames` = chế độ trình chiếu (FR-HM-09): thay tên bằng "SV 01…", bỏ MSSV. Dữ liệu ô lấy theo key nút (`statesByKey`).
 * Cột tên dính khi cuộn ngang. Thẻ: GD-10, GD-14.
 */
export function HeatGrid({ rows, nodes, hideNames = false }: { rows: Row[]; nodes: Stat[]; hideNames?: boolean }) {
  if (rows.length === 0) return <p className="rounded-lg border border-dashed border-line-strong p-4 text-body-m text-ink-500">Lớp chưa có sinh viên nào.</p>;
  return (
    <div className="overflow-x-auto rounded-lg border border-line-soft">
      <table aria-label="Lưới sinh viên theo nút" className="min-w-full border-collapse text-body-s">
        <thead>
          <tr className="bg-app">
            <th scope="col" className="sticky left-0 z-10 bg-app px-3 py-2 text-left font-semibold">
              Sinh viên
            </th>
            {nodes.map((n) => (
              <th key={n.nodeId} scope="col" title={n.title} className="px-2 py-2 text-center font-semibold">
                {n.code}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.studentId} className="border-t border-line-soft">
              <th scope="row" className="sticky left-0 z-10 whitespace-nowrap bg-surface px-3 py-2 text-left font-normal">
                {hideNames ? (
                  <span className="font-semibold">SV {String(i + 1).padStart(2, "0")}</span>
                ) : (
                  <>
                    <span className="font-semibold">{r.studentName}</span> <span className="text-ink-500">{r.studentCode}</span>
                  </>
                )}
              </th>
              {nodes.map((n) => (
                <td key={n.nodeId} className="px-1 py-1 text-center">
                  <Cell state={(n.nodeKey && r.statesByKey?.[n.nodeKey]) as MasteryState | undefined} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Cell({ state }: { state?: MasteryState }) {
  if (!state) return <span className="text-ink-300" aria-label="Chưa có dữ liệu">–</span>;
  const look = MASTERY[state];
  const Icon = look.icon;
  return (
    <span title={look.label} aria-label={look.label} className={`inline-flex size-7 items-center justify-center rounded-md border ${look.className}`}>
      <Icon aria-hidden size={14} strokeWidth={2.5} />
    </span>
  );
}
