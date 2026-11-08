import { useState } from "react";
import { Link } from "react-router";
import { HEAT, type HeatColor } from "../../lib/status";
import {
  BANDS,
  studentHeat,
  type NodeRate,
  type Row,
  type Stat,
  type Summary,
} from "../../lib/stats";

/** Màu nền cột/ô: đậm hơn token `bg-st-*` để nhìn rõ trên nền trắng; số và biểu tượng luôn đi kèm (NFR-12). */
export const FILL: Record<HeatColor, string> = {
  GREEN: "#4caf50",
  YELLOW: "#f2b134",
  RED: "#e0605e",
  GREY: "#b0bec5",
};
const pct = (v: number) => `${Math.round(v * 100)}%`;

export function SummaryTiles({ s }: { s: Summary }) {
  const items: [string, string][] = [
    ["Sĩ số đang xét", String(s.total)],
    ["Đã có dữ liệu", `${s.withData}/${s.total}`],
    ["Trung bình nút Đạt", s.avgPct == null ? "–" : `${s.avgPct}%`],
    ["Cần chú ý (< 40%)", String(s.attention)],
    ["Ô đang giảng", String(s.inProgress)],
    ["Trực tuyến", String(s.online)],
  ];
  return (
    <dl
      aria-label="Số liệu tổng quan"
      className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6"
    >
      {items.map(([t, v]) => (
        <div
          key={t}
          className="rounded-lg border border-line-soft bg-surface px-3 py-2"
        >
          <dt className="text-body-s text-ink-500">{t}</dt>
          <dd className="text-h3 font-bold">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Thanh phân bố SV theo nhóm màu; bấm một đoạn để lọc nhóm đó. */
export function DistributionBar({
  dist,
  total,
  active,
  onPick,
}: {
  dist: Record<HeatColor, number>;
  total: number;
  active?: HeatColor;
  onPick: (c?: HeatColor) => void;
}) {
  if (total === 0) return <Empty />;
  return (
    <div className="space-y-2">
      <div
        className="flex h-8 gap-0.5 overflow-hidden rounded-md"
        role="group"
        aria-label="Phân bố sinh viên theo nhóm màu"
      >
        {BANDS.filter((c) => dist[c] > 0).map((c) => (
          <button
            key={c}
            type="button"
            aria-pressed={active === c}
            onClick={() => onPick(active === c ? undefined : c)}
            aria-label={`${HEAT[c].label}: ${dist[c]} SV (${pct(dist[c] / total)})`} title={`${HEAT[c].label}: ${dist[c]} SV (${pct(dist[c] / total)})`}
            style={{ flex: dist[c], background: FILL[c] }}
            className={`flex items-center justify-center text-[12px] font-semibold text-white ${active && active !== c ? "opacity-40" : ""}`}
          >
            {dist[c] / total >= 0.07 ? pct(dist[c] / total) : ""}
          </button>
        ))}
      </div>
      <ul
        aria-label="Chú giải nhóm màu"
        className="flex flex-wrap gap-x-4 gap-y-1 text-body-s"
      >
        {BANDS.map((c) => {
          const Icon = HEAT[c].icon;
          return (
            <li key={c} className="flex items-center gap-1">
              <span
                aria-hidden
                className="inline-block size-3 rounded-sm"
                style={{ background: FILL[c] }}
              />
              <Icon aria-hidden size={12} /> {HEAT[c].label}:{" "}
              <strong>{dist[c]}</strong>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Nút yếu nhất: thanh ngang tỉ lệ Đạt, nút chưa đủ mẫu hiện xám kèm chữ. Bấm → GV-06 của nút. */
export function WeakestNodes({
  rates,
  classId,
}: {
  rates: NodeRate[];
  classId: string;
}) {
  const [all, setAll] = useState(false);
  if (rates.length === 0) return <Empty text="Không có nút nào khớp bộ lọc." />;
  const shown = all ? rates : rates.slice(0, 10);
  return (
    <div className="space-y-1">
      <ol aria-label="Nút yếu nhất" className="space-y-1">
        {shown.map((r) => (
          <li key={r.node.nodeId}>
            <Link
              to={`/gv/classes/${classId}/nodes/${r.node.nodeId}`}
              title={`${r.node.code} ${r.node.title}: ${r.passed}/${r.attempted} SV Đạt`}
              className="grid grid-cols-[9rem_1fr_3rem] items-center gap-2 rounded-md px-1 py-0.5 text-body-s hover:bg-app"
            >
              <span className="truncate">
                {r.node.isRootCause && (
                  <span aria-label="Nút gốc" title="Nút gốc">
                    ◎{" "}
                  </span>
                )}
                <strong>{r.node.code}</strong> {r.node.title}
              </span>
              <span className="relative h-4 rounded-sm bg-app">
                <span
                  className="absolute inset-y-0 left-0 rounded-sm"
                  style={{
                    width: r.rate == null ? "0%" : pct(r.rate),
                    background: FILL[r.color],
                  }}
                />
                <span
                  aria-hidden
                  className="absolute inset-y-0 left-[40%] border-l border-dashed border-ink-500/60"
                />
                <span
                  aria-hidden
                  className="absolute inset-y-0 left-[70%] border-l border-dashed border-ink-500/60"
                />
              </span>
              <span className="text-right font-semibold">
                {r.rate == null ? (
                  <span className="font-normal text-ink-500">
                    {r.sample === "NO_ATTEMPT" ? "chưa thử" : "ít mẫu"}
                  </span>
                ) : (
                  pct(r.rate)
                )}
              </span>
            </Link>
          </li>
        ))}
      </ol>
      {rates.length > 10 && (
        <button
          type="button"
          onClick={() => setAll(!all)}
          className="text-body-s font-semibold text-teal hover:underline"
        >
          {all ? "Chỉ hiện 10 nút yếu nhất" : `Xem tất cả ${rates.length} nút`}
        </button>
      )}
    </div>
  );
}

/** Phân tán: ngang = tỉ lệ SV đã thử, dọc = tỉ lệ Đạt. Góc trái-trên = nút học rồi mà trượt, dưới-trái = chưa ai học tới. */
export function NodeScatter({
  rates,
  classId,
}: {
  rates: NodeRate[];
  classId: string;
}) {
  const pts = rates.filter((r) => r.rate != null);
  const hidden = rates.length - pts.length;
  if (pts.length === 0) return <Empty text="Chưa nút nào đủ mẫu để vẽ." />;
  const W = 420,
    H = 260,
    L = 38,
    B = 34,
    T = 10,
    R = 12;
  const x = (v: number) => L + (W - L - R) * v;
  const y = (v: number) => T + (H - T - B) * (1 - v);
  return (
    <div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="group"
        aria-label="Biểu đồ phân tán tỉ lệ Đạt theo tỉ lệ đã thử của từng nút"
        className="w-full overflow-visible"
      >
        {[0, 0.25, 0.5, 0.75, 1].map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke="#e3e7ee" />
            <text
              x={L - 6}
              y={y(v) + 4}
              textAnchor="end"
              fontSize="11"
              fill="#6b7a90"
            >
              {pct(v)}
            </text>
            <text
              x={x(v)}
              y={H - 16}
              textAnchor="middle"
              fontSize="11"
              fill="#6b7a90"
            >
              {pct(v)}
            </text>
          </g>
        ))}
        {[0.4, 0.7].map((v) => (
          <line
            key={v}
            x1={L}
            x2={W - R}
            y1={y(v)}
            y2={y(v)}
            stroke="#6b7a90"
            strokeDasharray="4 3"
          />
        ))}
        <text x={W - R} y={H - 2} textAnchor="end" fontSize="11" fill="#6b7a90">
          Tỉ lệ SV đã thử nút →
        </text>
        <text x={L + 4} y={T + 10} fontSize="11" fill="#6b7a90">
          Tỉ lệ Đạt ↑
        </text>
        {pts.map((r) => (
          <Link
            key={r.node.nodeId}
            to={`/gv/classes/${classId}/nodes/${r.node.nodeId}`}
            aria-label={`${r.node.code} ${r.node.title}: đã thử ${pct(r.attemptedRate)}, Đạt ${pct(r.rate ?? 0)}`}
          >
            <circle
              cx={x(r.attemptedRate)}
              cy={y(r.rate ?? 0)}
              r={7}
              fill={FILL[r.color]}
              stroke="#fff"
              strokeWidth={2}
            >
              <title>{`${r.node.code} ${r.node.title} – đã thử ${pct(r.attemptedRate)}, Đạt ${pct(r.rate ?? 0)}`}</title>
            </circle>
          </Link>
        ))}
      </svg>
      {hidden > 0 && (
        <p className="text-body-s text-ink-500">
          {hidden} nút chưa đủ mẫu nên chưa vẽ.
        </p>
      )}
    </div>
  );
}

/** Tỉ lệ Đạt theo chương hoặc mức Bloom. Bấm một cột để lọc. */
export function GroupBars({
  data,
  active,
  onPick,
}: {
  data: {
    label: string;
    rate: number | null;
    nodes: number;
    attempted: number;
  }[];
  active?: string;
  onPick: (label?: string) => void;
}) {
  if (data.length === 0) return <Empty />;
  return (
    <ul aria-label="Tỉ lệ Đạt theo nhóm" className="space-y-1">
      {data.map((d) => {
        const c: HeatColor =
          d.rate == null
            ? "GREY"
            : d.rate >= 0.7
              ? "GREEN"
              : d.rate >= 0.4
                ? "YELLOW"
                : "RED";
        return (
          <li key={d.label}>
            <button
              type="button"
              aria-pressed={active === d.label}
              onClick={() => onPick(active === d.label ? undefined : d.label)}
              title={`${d.label}: ${d.nodes} nút, ${d.attempted} lượt thử`}
              className={`grid w-full grid-cols-[8rem_1fr_3rem] items-center gap-2 rounded-md px-1 py-0.5 text-left text-body-s hover:bg-app ${active && active !== d.label ? "opacity-50" : ""}`}
            >
              <span className="truncate">{d.label}</span>
              <span className="h-4 rounded-sm bg-app">
                <span
                  className="block h-full rounded-sm"
                  style={{
                    width: d.rate == null ? "0%" : pct(d.rate),
                    background: FILL[c],
                  }}
                />
              </span>
              <span className="text-right font-semibold">
                {d.rate == null ? (
                  <span className="font-normal text-ink-500">ít mẫu</span>
                ) : (
                  pct(d.rate)
                )}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/** Khung ô màu: mỗi SV một ô nhỏ. Bấm ô → hồ sơ năng lực SV (GV-07); chi tiết từng nút xem ở tab "Lưới SV × Nút". */
export function StudentTiles({
  rows,
  nodes,
  classId,
  hideNames,
}: {
  rows: Row[];
  nodes: Stat[];
  classId: string;
  hideNames: boolean;
}) {
  if (rows.length === 0)
    return <Empty text="Không có sinh viên nào khớp bộ lọc." />;
  return (
    <ul
      aria-label="Khung màu sinh viên"
      className="grid max-h-[50vh] gap-1.5 overflow-y-auto rounded-lg border border-line-soft bg-app p-2"
      style={{ gridTemplateColumns: "repeat(auto-fill, minmax(3.5rem, 1fr))" }}
    >
      {rows.map((r, i) => {
        const h = studentHeat(r, nodes);
        const Icon = HEAT[h.color].icon;
        const name = hideNames
          ? `SV ${String(i + 1).padStart(2, "0")}`
          : `${r.studentName} ${r.studentCode}`;
        const tile = (
          <span
            aria-label={`${name}: ${h.pct == null ? HEAT[h.color].label : `${h.pct}% nút Đạt`}`}
            title={`${name} – ${h.passed}/${nodes.length} nút Đạt`}
            className="flex h-12 flex-col items-center justify-center rounded-md text-[11px] leading-tight text-white"
            style={{ background: FILL[h.color] }}
          >
            <Icon aria-hidden size={12} strokeWidth={2.5} />
            <span className="font-semibold">
              {h.pct == null ? "–" : `${h.pct}%`}
            </span>
            <span className="max-w-full truncate px-0.5 opacity-80">
              {hideNames
                ? String(i + 1).padStart(2, "0")
                : r.studentCode.slice(-4)}
            </span>
          </span>
        );
        return (
          <li key={r.studentId}>
            {hideNames ? (
              tile
            ) : (
              <Link to={`/gv/classes/${classId}/students/${r.studentId}`}>
                {tile}
              </Link>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function Empty({ text = "Chưa có dữ liệu." }: { text?: string }) {
  return (
    <p className="rounded-lg border border-dashed border-line-strong p-3 text-body-s text-ink-500">
      {text}
    </p>
  );
}
