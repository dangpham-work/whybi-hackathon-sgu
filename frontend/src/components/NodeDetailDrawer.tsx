import { ExternalLink, Flame, Search, Target, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { apiCall, type Schema } from "../lib/api";
import { HEAT, MASTERY, type HeatColor, type MasteryState } from "../lib/status";
import { useApi } from "../lib/useApi";

type Detail = Schema<"NodeDetail">;
type Stat = Schema<"NodeStat">;
type StudentRow = Detail["studentsByState"][string][number];

const STATE_ORDER: MasteryState[] = [
  "NOT_PASSED",
  "IN_PROGRESS",
  "MASTERED",
  "NEEDS_REVERIFY",
  "AVAILABLE",
  "LOCKED",
];

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

/** Khung chi tiết nút trượt ra ở bên trái bản đồ nhiệt cây (GV-05). */
export function NodeDetailDrawer({
  classId,
  nodeId,
  initialStat,
  onClose,
  hideNames = false,
  onSelectNode,
}: {
  classId: string;
  nodeId: string;
  initialStat?: Stat;
  onClose: () => void;
  hideNames?: boolean;
  onSelectNode?: (nodeId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const detailApi = useApi(
    (signal) =>
      apiCall("get", "/classes/{class_id}/nodes/{node_id}/detail", {
        path: { class_id: classId, node_id: nodeId },
        query: { anonymize: hideNames },
        signal,
      }),
    [classId, nodeId, hideNames]
  );

  const stat = detailApi.data?.stat ?? initialStat;
  const d = detailApi.data;

  const heat = stat ? HEAT[stat.color as HeatColor] : null;
  const HeatIcon = heat?.icon ?? Flame;
  const attemptedPct = stat?.attemptedRate != null ? Math.round(stat.attemptedRate * 100) : null;
  const passPct = stat?.passRate != null ? Math.round(stat.passRate * 100) : null;

  const dedupedByState = d
    ? (Object.fromEntries(
        STATE_ORDER.map((st) => [st, dedupStudents(d.studentsByState[st])])
      ) as Record<MasteryState, StudentRow[]>)
    : null;

  const total = dedupedByState
    ? Object.values(dedupedByState).reduce((n, l) => n + l.length, 0)
    : 0;

  const needle = query.trim().toLowerCase();

  return (
    <div className="flex h-full flex-col space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-2 border-b border-line-soft pb-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 mb-1">
            {heat && (
              <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-body-xs font-semibold ${heat.className}`}>
                <HeatIcon aria-hidden size={12} /> {stat?.label ?? heat.label}
              </span>
            )}
            {stat?.isRootCause && (
              <span className="inline-flex items-center gap-1 rounded-full bg-ink-900 px-2 py-0.5 text-body-xs font-semibold text-honey">
                <Target aria-hidden size={12} /> Điểm nghẽn gốc
              </span>
            )}
          </div>
          <h2 className="text-h3 font-bold truncate text-ink-900">
            {stat ? `${stat.code} – ${stat.title}` : "Chi tiết nút kỹ năng"}
          </h2>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <Link
            to={`/gv/classes/${classId}/nodes/${nodeId}`}
            title="Mở toàn màn hình chi tiết nút"
            aria-label="Mở toàn màn hình chi tiết nút"
            className="rounded-md border border-line-strong p-1.5 text-ink-500 hover:bg-app hover:text-ink-900"
          >
            <ExternalLink size={16} />
          </Link>
          <button
            type="button"
            onClick={onClose}
            title="Đóng chi tiết nút"
            aria-label="Đóng chi tiết nút"
            className="rounded-md border border-line-strong p-1.5 text-ink-500 hover:bg-app hover:text-ink-900"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Quick Stats Grid */}
      {stat && (
        <dl className="grid grid-cols-2 gap-2 rounded-lg bg-app p-3 text-body-s">
          <div className="space-y-0.5">
            <dt className="text-ink-500 text-body-xs">Đã thử</dt>
            <dd className="font-bold text-ink-900">
              {stat.attemptedCount}/{stat.enrolledCount ?? total} SV
            </dd>
          </div>
          <div className="space-y-0.5">
            <dt className="text-ink-500 text-body-xs">Tỉ lệ đã thử</dt>
            <dd className="font-bold text-ink-900">
              {attemptedPct == null ? "–" : `${attemptedPct}%`}
            </dd>
          </div>
          <div className="space-y-0.5">
            <dt className="text-ink-500 text-body-xs">Tỉ lệ Đạt</dt>
            <dd className="font-bold text-teal">
              {passPct == null ? "–" : `${passPct}%`} ({stat.passedCount} SV)
            </dd>
          </div>
          <div className="space-y-0.5">
            <dt className="text-ink-500 text-body-xs">Chưa đạt</dt>
            <dd className="font-bold text-red-700">
              {stat.attemptedCount - stat.passedCount} SV
            </dd>
          </div>
        </dl>
      )}

      {/* Alert if root cause */}
      {d?.alert && (
        <section
          aria-label="Truy vết điểm nghẽn gốc"
          className="space-y-2 rounded-lg border border-red-700/40 bg-st-fail/30 p-3 text-body-s"
        >
          <h3 className="text-body-xs font-bold uppercase tracking-wider text-red-900">
            Truy vết điểm nghẽn gốc
          </h3>
          <p className="font-bold text-red-900">{d.alert.message}</p>
          {d.alert.conditionalFailRate != null && (
            <p className="text-body-xs text-ink-700">
              {Math.round(d.alert.conditionalFailRate * 100)}% SV trượt nút này cũng chưa Đạt nút gốc.
            </p>
          )}
          {d.alert.rootCauseNodeId && d.alert.rootCauseNodeId !== nodeId && (
            <button
              type="button"
              onClick={() => onSelectNode?.(d.alert!.rootCauseNodeId)}
              className="inline-flex items-center gap-1 rounded-md border border-red-700/50 bg-surface px-2.5 py-1 text-body-xs font-semibold text-red-900 hover:bg-red-50"
            >
              Chuyển tới nút gốc
            </button>
          )}
        </section>
      )}

      {/* Students By State List */}
      <section
        aria-label="Sinh viên theo trạng thái"
        className="flex-1 space-y-3 overflow-y-auto pr-1"
      >
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-body-xs font-bold text-ink-700 uppercase tracking-wider">
            Sinh viên theo trạng thái
          </h3>
          {total > 0 && (
            <div className="relative">
              <Search size={14} className="absolute left-2 top-2 text-ink-400" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Tìm tên..."
                aria-label="Tìm sinh viên theo tên"
                className="w-32 rounded-md border border-line-strong bg-surface pl-6 pr-2 py-1 text-body-xs text-ink-900 outline-none placeholder:text-ink-400 focus:border-teal"
              />
            </div>
          )}
        </div>

        {dedupedByState ? (
          STATE_ORDER.filter((st) => dedupedByState[st]?.length > 0).map((st) => {
            const look = MASTERY[st];
            const Icon = look.icon;
            const allList = dedupedByState[st];
            const list = needle
              ? allList.filter(
                  (r) =>
                    r.studentName.toLowerCase().includes(needle) ||
                    (r.studentCode ?? "").toLowerCase().includes(needle)
                )
              : allList;
            if (needle && list.length === 0) return null;
            const isExpanded = !!expanded[st] || !!needle;
            const shown = isExpanded ? list : list.slice(0, 8);
            const hasMore = list.length > 8 && !needle;

            return (
              <div key={st} className="rounded-md border border-line-soft bg-surface p-2.5 space-y-2">
                <div className="flex items-center justify-between">
                  <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-body-xs font-semibold ${look.className}`}>
                    <Icon aria-hidden size={12} /> {look.label} ({list.length})
                  </span>
                  {hasMore && (
                    <button
                      type="button"
                      onClick={() => setExpanded((prev) => ({ ...prev, [st]: !isExpanded }))}
                      className="text-body-xs font-semibold text-teal hover:underline"
                    >
                      {isExpanded ? "Thu gọn" : `Xem tất cả (${list.length})`}
                    </button>
                  )}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {shown.map((r, i) =>
                    hideNames ? (
                      <span key={r.studentId || `${r.studentName}-${i}`} className="rounded bg-app px-2 py-0.5 text-body-xs text-ink-900">
                        SV {i + 1}
                      </span>
                    ) : (
                      <Link
                        key={r.studentId || `${r.studentName}-${i}`}
                        to={`/gv/classes/${classId}/students/${r.studentId}`}
                        title="Xem hồ sơ năng lực sinh viên"
                        className="rounded bg-app px-2 py-0.5 text-body-xs font-medium text-ink-900 hover:bg-teal-soft hover:text-teal transition-colors"
                      >
                        {r.studentName}
                      </Link>
                    )
                  )}
                </div>
              </div>
            );
          })
        ) : (
          <p className="text-body-s text-ink-500 py-2">Đang tải danh sách sinh viên...</p>
        )}

        {/* Misconceptions */}
        {d?.topMisconceptions && d.topMisconceptions.length > 0 && (
          <div className="rounded-lg bg-app p-3 space-y-2">
            <h3 className="text-body-xs font-bold text-ink-700 uppercase tracking-wider">
              Quan niệm sai phổ biến
            </h3>
            {d.topMisconceptions.map((m, i) => {
              const text = String(m.content ?? m.text ?? m.id ?? "");
              const count = Number(m.count ?? m.studentCount ?? 0);
              return (
                <div key={i} className="space-y-1 text-body-xs">
                  <div className="flex justify-between">
                    <span className="text-ink-800">{text}</span>
                    <strong className="text-ink-900">{count} SV</strong>
                  </div>
                  <div aria-hidden className="h-1 rounded-full bg-line-soft">
                    <div
                      className="h-full rounded-full bg-red-600"
                      style={{
                        width: `${Math.min(100, (count / Math.max(1, stat?.attemptedCount ?? 1)) * 100)}%`,
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
