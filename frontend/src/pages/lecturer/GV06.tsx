import { Search, Target } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { AsyncView } from "../../components/AsyncView";
import { apiCall, type Schema } from "../../lib/api";
import { HEAT, MASTERY, type HeatColor, type MasteryState } from "../../lib/status";
import { useApi } from "../../lib/useApi";

type Detail = Schema<"NodeDetail">;
type StudentRow = Detail["studentsByState"][string][number];
const STATE_ORDER: MasteryState[] = ["NOT_PASSED", "IN_PROGRESS", "MASTERED", "NEEDS_REVERIFY", "AVAILABLE", "LOCKED"];
const COLLAPSED_LIMIT = 10;

function dedupStudents(rows: StudentRow[] = []): StudentRow[] {
  const seenIds = new Set<string>();
  const seenNames = new Set<string>();
  const out: StudentRow[] = [];
  for (const r of rows) {
    const idKey = r.studentId?.trim();
    const nameKey = `${r.studentName.trim().toLowerCase()}::${(r.studentCode ?? "").trim().toLowerCase()}`;
    if ((idKey && seenIds.has(idKey)) || seenNames.has(nameKey)) continue;
    if (idKey) seenIds.add(idKey);
    seenNames.add(nameKey);
    out.push(r);
  }
  return out;
}

/** GV-06 Chi tiết nút & điểm nghẽn (Figma 19:1460, FR-HM-06, GD-10). */
export default function LecturerNodeDetail() {
  const { classId = "", nodeId = "" } = useParams();
  const detail = useApi((signal) => apiCall("get", "/classes/{class_id}/nodes/{node_id}/detail", { path: { class_id: classId, node_id: nodeId }, signal }), [classId, nodeId]);
  return (
    <div className="space-y-5 p-4 lg:p-7">
      <AsyncView state={detail} loadingText="Đang tải chi tiết nút…">
        {(d) => <View d={d} classId={classId} />}
      </AsyncView>
    </div>
  );
}

function View({ d, classId }: { d: Detail; classId: string }) {
  const [anonymize] = useState(false);
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const stat = d.stat;
  const heat = HEAT[stat.color as HeatColor];
  const HeatIcon = heat.icon;
  const attemptedPct = stat.attemptedRate != null ? Math.round(stat.attemptedRate * 100) : null;
  const dedupedByState = Object.fromEntries(STATE_ORDER.map((st) => [st, dedupStudents(d.studentsByState[st])])) as Record<MasteryState, StudentRow[]>;
  const total = Object.values(dedupedByState).reduce((n, l) => n + l.length, 0);
  const needle = query.trim().toLowerCase();
  return (
    <>
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-h1 font-bold">
          {stat.code} – {stat.title}
        </h1>
        <span className={`inline-flex items-center gap-1 rounded-full border px-3 py-1 text-body-s font-semibold ${heat.className}`}>
          <HeatIcon aria-hidden size={14} /> {stat.label ?? heat.label}
        </span>
        {stat.isRootCause && (
          <span className="inline-flex items-center gap-1 rounded-full bg-ink-900 px-3 py-1 text-body-s font-semibold text-honey">
            <Target aria-hidden size={14} /> Điểm nghẽn gốc
          </span>
        )}
        <Link to={`/gv/classes/${classId}/heatmap`} className="ml-auto text-body-m font-semibold text-teal hover:underline">
          ← Về bản đồ nhiệt
        </Link>
      </header>

      <dl className="grid grid-cols-2 gap-3 rounded-lg bg-app p-4 sm:grid-cols-4">
        <Fact label="Đã thử" value={`${stat.attemptedCount}/${stat.enrolledCount ?? total}`} />
        <Fact label="Tỉ lệ đã thử" value={attemptedPct == null ? "–" : `${attemptedPct}%`} />
        <Fact label="Đạt" value={stat.passedCount} />
        <Fact label="Chưa đạt" value={stat.attemptedCount - stat.passedCount} />
      </dl>

      <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
        <section aria-label="Sinh viên theo trạng thái" className="space-y-3 rounded-lg border border-line-soft bg-surface p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="caps">Sinh viên theo trạng thái</h2>
            {total > 0 && (
              <label className="flex items-center gap-2 rounded-md border border-line-strong px-2.5 py-1 text-body-s text-ink-500">
                <Search aria-hidden size={14} />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Tìm sinh viên…"
                  aria-label="Tìm sinh viên"
                  className="w-44 bg-transparent text-ink-900 outline-none placeholder:text-ink-300"
                />
              </label>
            )}
          </div>
          {STATE_ORDER.filter((st) => dedupedByState[st]?.length).map((st) => {
            const look = MASTERY[st];
            const Icon = look.icon;
            const allList = dedupedByState[st];
            const list = needle
              ? allList.filter((r) => r.studentName.toLowerCase().includes(needle) || (r.studentCode ?? "").toLowerCase().includes(needle))
              : allList;
            if (needle && list.length === 0) return null;
            const isExpanded = !!expanded[st] || !!needle;
            const shown = isExpanded ? list : list.slice(0, COLLAPSED_LIMIT);
            const hasMore = list.length > COLLAPSED_LIMIT && !needle;
            return (
              <div key={st} className="flex flex-col gap-2 border-t border-line-soft py-2.5 first:border-0 sm:flex-row sm:items-start sm:gap-3">
                <span className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-3 py-1 text-body-s font-semibold ${look.className}`}>
                  <Icon aria-hidden size={14} /> {look.label} ({list.length})
                </span>
                <div className="flex flex-1 flex-wrap items-center gap-1.5">
                  {shown.map((r, i) => (
                    <span key={r.studentId || `${r.studentName}-${i}`} className="rounded-md bg-app px-2 py-0.5 text-body-s text-ink-900">
                      {anonymize ? `SV ${i + 1}` : r.studentName}
                    </span>
                  ))}
                  {hasMore && (
                    <button
                      type="button"
                      onClick={() => setExpanded((prev) => ({ ...prev, [st]: !isExpanded }))}
                      className="rounded-md px-2 py-0.5 text-body-s font-semibold text-teal hover:underline"
                    >
                      {isExpanded ? "Thu gọn" : `Xem tất cả (${list.length})`}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
          {total === 0 && <p className="text-body-m text-ink-500">Chưa có sinh viên nào ở nút này.</p>}
        </section>

        <div className="space-y-4">
          <section aria-label="Quan niệm sai phổ biến" className="space-y-2 rounded-lg bg-app p-4">
            <h2 className="caps">Quan niệm sai phổ biến</h2>
            {d.topMisconceptions.length === 0 && <p className="text-body-m text-ink-500">Chưa ghi nhận quan niệm sai nào.</p>}
            {d.topMisconceptions.map((m, i) => {
              const text = String(m.content ?? m.text ?? m.id ?? "");
              const count = Number(m.count ?? m.studentCount ?? 0);
              return (
                <div key={i} className="space-y-1">
                  <div className="flex justify-between text-body-m">
                    <span>{text}</span>
                    <strong>{count} SV</strong>
                  </div>
                  <div aria-hidden className="h-1.5 rounded-full bg-line-soft">
                    <div className="h-full rounded-full bg-red-600" style={{ width: `${Math.min(100, (count / Math.max(1, stat.attemptedCount)) * 100)}%` }} />
                  </div>
                </div>
              );
            })}
          </section>
          {d.alert && (
            <section aria-label="Truy vết điểm nghẽn gốc" className="space-y-2 rounded-lg border border-red-700/40 bg-st-fail/30 p-4">
              <h2 className="caps text-red-900">Truy vết điểm nghẽn gốc</h2>
              <p className="font-semibold text-red-900">{d.alert.message}</p>
              {d.alert.conditionalFailRate != null && (
                <p className="text-body-s">
                  Tỉ lệ trượt có điều kiện r = {d.alert.conditionalFailRate.toFixed(2).replace(".", ",")}.
                </p>
              )}
              {d.alert.rootCauseNodeId !== d.nodeId && (
                <Link to={`/gv/classes/${classId}/nodes/${d.alert.rootCauseNodeId}`} className="text-body-m font-semibold text-red-900 underline">
                  Xem nút gốc {d.alert.rootCauseTitle ?? ""}
                </Link>
              )}
              <Link to={`/gv/classes/${classId}/matching`} className="block text-body-m font-semibold text-teal hover:underline">
                Ghép cặp ưu tiên nút này
              </Link>
            </section>
          )}
        </div>
      </div>
    </>
  );
}

function Fact({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dd className="text-h1 font-bold">{value}</dd>
      <dt className="caps">{label}</dt>
    </div>
  );
}
