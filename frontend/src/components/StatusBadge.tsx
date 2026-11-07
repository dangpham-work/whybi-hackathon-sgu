import { HEAT, MASTERY, ROOT_CAUSE, type HeatColor, type MasteryState } from "../lib/status";

type Props =
  | { kind: "mastery"; value: MasteryState; label?: string }
  | { kind: "heat"; value: HeatColor; label?: string }
  | { kind: "root"; label?: string };

/** Huy hiệu trạng thái (Figma mục 04 "Huy hiệu trạng thái"): màu + biểu tượng + chữ. */
export function StatusBadge(props: Props) {
  const look = props.kind === "mastery" ? MASTERY[props.value] : props.kind === "heat" ? HEAT[props.value] : ROOT_CAUSE;
  const Icon = look.icon;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-body-s font-semibold ${look.className}`}
    >
      <Icon aria-hidden size={12} strokeWidth={2.5} />
      {props.label ?? look.label}
    </span>
  );
}

export function StatusLegend({ kind }: { kind: "mastery" | "heat" }) {
  const entries = kind === "mastery" ? Object.keys(MASTERY) : Object.keys(HEAT);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="caps">Chú giải</span>
      {entries.map((v) =>
        kind === "mastery" ? (
          <StatusBadge key={v} kind="mastery" value={v as MasteryState} />
        ) : (
          <StatusBadge key={v} kind="heat" value={v as HeatColor} />
        ),
      )}
      {kind === "heat" && <StatusBadge kind="root" />}
    </div>
  );
}
