import { Download, X } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";
import {
  activeFilterCount,
  distribution,
  filterNodes,
  filterStudents,
  filtersFromParams,
  filtersToParams,
  groupRates,
  nodeMeta,
  nodeRates,
  summarize,
  toCsv,
  weakest,
  type Filters,
  type Snapshot,
} from "../../lib/stats";
import { HEAT } from "../../lib/status";
import { BLOOM_LABEL } from "../SkillTree";
import {
  DistributionBar,
  GroupBars,
  NodeScatter,
  StudentTiles,
  SummaryTiles,
  WeakestNodes,
} from "./StatsCharts";

const NODE_STATE_LABEL = {
  PASSED: "Đã Đạt",
  NOT_PASSED: "Chưa đạt",
  IN_PROGRESS: "Đang giảng",
} as const;
const field =
  "rounded-md border border-line-strong bg-surface px-2 py-1.5 text-body-s";
const bloomLabel = (b: string) =>
  BLOOM_LABEL[b as keyof typeof BLOOM_LABEL] ?? b;

/**
 * Tab "Thống kê" của GV-05: bộ lọc nhiều đối tượng (lưu trên URL) + biểu đồ tính từ ảnh chụp heatmap.
 * Bấm vào biểu đồ = thêm bộ lọc (lọc chéo) hoặc mở GV-06 / GV-07. Chi tiết từng nút của SV nằm ở tab "Lưới SV × Nút".
 */
export function StatsTab({
  s,
  classId,
  hideNames,
}: {
  s: Snapshot;
  classId: string;
  hideNames: boolean;
}) {
  const [params, setParams] = useSearchParams();
  const f = filtersFromParams(params);
  const [by, setBy] = useState<"chapter" | "bloom">("chapter");
  const set = (patch: Partial<Filters>) =>
    setParams(filtersToParams({ ...f, ...patch }, params), { replace: true });
  const clear = () => setParams(filtersToParams({}, params), { replace: true });

  const eff: Filters = hideNames ? { ...f, q: undefined } : f; // đang ẩn tên thì không lọc theo tên
  const meta = useMemo(() => nodeMeta(s), [s]);
  const chapters = [...new Set([...meta.values()].map((m) => m.chapter))];
  const blooms = [...new Set([...meta.values()].map((m) => m.bloom))];

  const nodes = filterNodes(s, eff);
  const rowsAll = filterStudents(s, { ...eff, group: undefined }, nodes);
  const rows = eff.group ? filterStudents(s, eff, nodes) : rowsAll;
  const studentsFiltered = Boolean(
    eff.q || (eff.nodeKey && eff.nodeState) || eff.group,
  );
  const rates = nodeRates(s, nodes, rows, studentsFiltered);

  function exportCsv() {
    const a = document.createElement("a");
    const url = URL.createObjectURL(
      new Blob([toCsv(rows, nodes, hideNames)], {
        type: "text/csv;charset=utf-8",
      }),
    );
    a.href = url;
    a.download = "thong-ke-lop.csv";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const chips: [string, string, () => void][] = [];
  if (eff.group)
    chips.push([
      `Nhóm SV: ${HEAT[eff.group].label}`,
      "group",
      () => set({ group: undefined }),
    ]);
  if (eff.q) chips.push([`Tìm: ${eff.q}`, "q", () => set({ q: undefined })]);
  if (eff.chapter)
    chips.push([eff.chapter, "chapter", () => set({ chapter: undefined })]);
  if (eff.bloom)
    chips.push([
      `Bloom: ${bloomLabel(eff.bloom)}`,
      "bloom",
      () => set({ bloom: undefined }),
    ]);
  if (eff.nodeColor)
    chips.push([
      `Nút ${HEAT[eff.nodeColor].label}`,
      "nodeColor",
      () => set({ nodeColor: undefined }),
    ]);
  if (eff.rootOnly)
    chips.push([
      "Chỉ nút gốc ◎",
      "rootOnly",
      () => set({ rootOnly: undefined }),
    ]);
  if (eff.nodeKey && eff.nodeState)
    chips.push([
      `${eff.nodeKey.toUpperCase()}: ${NODE_STATE_LABEL[eff.nodeState]}`,
      "node",
      () => set({ nodeKey: undefined, nodeState: undefined }),
    ]);

  const colorOptions = (["GREEN", "YELLOW", "RED", "GREY"] as const).map(
    (c) => [c, HEAT[c].label] as const,
  );
  return (
    <div className="space-y-4">
      <section
        aria-label="Bộ lọc thống kê"
        className="space-y-2 rounded-lg border border-line-soft bg-surface p-3"
      >
        <div className="flex flex-wrap items-center gap-2">
          {!hideNames && (
            <input
              aria-label="Lọc theo tên hoặc MSSV"
              placeholder="Tên / MSSV"
              value={f.q ?? ""}
              onChange={(e) => set({ q: e.target.value || undefined })}
              className={`${field} w-36`}
            />
          )}
          <Select
            label="Chương"
            value={f.chapter}
            onChange={(v) => set({ chapter: v })}
            options={chapters.map((c) => [c, c] as const)}
          />
          <Select
            label="Mức Bloom"
            value={f.bloom}
            onChange={(v) => set({ bloom: v })}
            options={blooms.map((b) => [b, bloomLabel(b)] as const)}
          />
          <Select
            label="Màu nút"
            value={f.nodeColor}
            onChange={(v) => set({ nodeColor: v as Filters["nodeColor"] })}
            options={colorOptions}
          />
          <Select
            label="Nhóm SV"
            value={f.group}
            onChange={(v) => set({ group: v as Filters["group"] })}
            options={colorOptions}
          />
          <Select
            label="SV tại nút"
            value={f.nodeKey}
            onChange={(v) =>
              set({
                nodeKey: v,
                nodeState: v ? (f.nodeState ?? "NOT_PASSED") : undefined,
              })
            }
            options={s.nodes
              .filter((n) => n.nodeKey)
              .map(
                (n) => [n.nodeKey as string, `${n.code} ${n.title}`] as const,
              )}
          />
          {f.nodeKey && (
            <Select
              label="Trạng thái"
              value={f.nodeState}
              onChange={(v) => set({ nodeState: v as Filters["nodeState"] })}
              options={Object.entries(NODE_STATE_LABEL)}
            />
          )}
          <label className="flex items-center gap-1 text-body-s">
            <input
              type="checkbox"
              checked={Boolean(f.rootOnly)}
              onChange={(e) => set({ rootOnly: e.target.checked || undefined })}
            />{" "}
            Chỉ nút gốc ◎
          </label>
          <button
            type="button"
            onClick={exportCsv}
            className="ml-auto inline-flex items-center gap-1 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-body-s font-semibold"
          >
            <Download aria-hidden size={14} /> Xuất CSV theo bộ lọc
          </button>
        </div>
        {activeFilterCount(eff) > 0 && (
          <ul
            aria-label="Bộ lọc đang bật"
            className="flex flex-wrap items-center gap-2"
          >
            {chips.map(([label, key, off]) => (
              <li
                key={key}
                className="flex items-center gap-1 rounded-full bg-teal-soft px-3 py-0.5 text-body-s text-teal"
              >
                {label}
                <button
                  type="button"
                  aria-label={`Bỏ lọc ${label}`}
                  onClick={off}
                >
                  <X aria-hidden size={12} />
                </button>
              </li>
            ))}
            <li>
              <button
                type="button"
                onClick={clear}
                className="text-body-s font-semibold text-teal hover:underline"
              >
                Xóa lọc
              </button>
            </li>
          </ul>
        )}
      </section>

      <SummaryTiles s={summarize(s, rows, nodes)} />

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <Card
          title="Phân bố sinh viên theo nhóm màu"
          hint="Bấm một đoạn để lọc nhóm đó."
        >
          <DistributionBar
            dist={distribution(rowsAll, nodes)}
            total={rowsAll.length}
            active={eff.group}
            onPick={(c) => set({ group: c })}
          />
        </Card>
        <Card
          title="Nút yếu nhất"
          hint="Tỉ lệ SV đã Đạt, thấp nhất lên đầu. Vạch đứt: 40% và 70%. Bấm để xem chi tiết nút."
        >
          <WeakestNodes rates={weakest(rates)} classId={classId} />
        </Card>
        <Card
          title="Nút nào học rồi mà trượt, nút nào chưa ai học tới?"
          hint="Ngang: tỉ lệ SV đã thử. Dọc: tỉ lệ Đạt. Trái-trên là điểm nghẽn thật."
        >
          <NodeScatter rates={rates} classId={classId} />
        </Card>
        <Card
          title={
            by === "chapter"
              ? "Tỉ lệ Đạt theo chương"
              : "Tỉ lệ Đạt theo mức Bloom"
          }
          hint="Bấm một dòng để lọc."
          action={
            <div
              role="group"
              aria-label="Gộp theo"
              className="inline-flex gap-1 rounded-md bg-app p-0.5"
            >
              {(["chapter", "bloom"] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  aria-pressed={by === k}
                  onClick={() => setBy(k)}
                  className={`rounded px-2 py-0.5 text-body-s font-semibold ${by === k ? "bg-surface shadow-card" : "text-ink-500"}`}
                >
                  {k === "chapter" ? "Chương" : "Bloom"}
                </button>
              ))}
            </div>
          }
        >
          <GroupBars
            data={groupRates(s, rates, by).map((d) =>
              by === "bloom" ? { ...d, label: bloomLabel(d.label) } : d,
            )}
            active={
              by === "chapter"
                ? f.chapter
                : f.bloom
                  ? bloomLabel(f.bloom)
                  : undefined
            }
            onPick={(label) =>
              by === "chapter"
                ? set({ chapter: label })
                : set({
                    bloom: label
                      ? blooms.find((b) => bloomLabel(b) === label)
                      : undefined,
                  })
            }
          />
        </Card>
      </div>

      <Card
        title={`Sinh viên (${rows.length})`}
        hint="Mỗi ô một sinh viên, màu theo tỉ lệ nút Đạt. Bấm ô để mở hồ sơ năng lực."
      >
        <StudentTiles
          rows={rows}
          nodes={nodes}
          classId={classId}
          hideNames={hideNames}
        />
      </Card>
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value?: string;
  onChange: (v?: string) => void;
  options: readonly (readonly [string, string])[];
}) {
  return (
    <select
      aria-label={label}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value || undefined)}
      className={field}
    >
      <option value="">{label}: tất cả</option>
      {options.map(([v, l]) => (
        <option key={v} value={v}>
          {l}
        </option>
      ))}
    </select>
  );
}

function Card({
  title,
  hint,
  action,
  children,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="space-y-2 rounded-lg border border-line-soft bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-h3 font-semibold">{title}</h2>
          {hint && <p className="text-body-s text-ink-500">{hint}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
