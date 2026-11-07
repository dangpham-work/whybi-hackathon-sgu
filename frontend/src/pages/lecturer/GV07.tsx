import { Link, useParams } from "react-router";
import { AsyncView } from "../../components/AsyncView";
import { apiCall, type Schema } from "../../lib/api";
import { MASTERY, type MasteryState } from "../../lib/status";
import { useApi } from "../../lib/useApi";

type Profile = Schema<"StudentProfile">;

const vn = (iso: string) => new Date(iso).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
const initials = (name: string) => name.split(/\s+/).slice(-2).map((w) => w[0]).join("").toUpperCase();

/** GV-07 Hồ sơ năng lực SV (Figma 19:1885, FR-HM-07, GD-13). */
export default function LecturerStudentProfile() {
  const { classId = "", studentId = "" } = useParams();
  const profile = useApi((signal) => apiCall("get", "/classes/{class_id}/students/{student_id}/profile", { path: { class_id: classId, student_id: studentId }, signal }), [classId, studentId]);
  const tree = useApi((signal) => apiCall("get", "/classes/{class_id}/tree", { path: { class_id: classId }, signal }), [classId]);
  return (
    <div className="space-y-5 p-4 lg:p-7">
      <AsyncView state={profile} loadingText="Đang tải hồ sơ…">
        {(p) => <View p={p} classId={classId} nodes={tree.data?.nodes ?? []} />}
      </AsyncView>
    </div>
  );
}

function View({ p, classId, nodes }: { p: Profile; classId: string; nodes: Schema<"Node">[] }) {
  const graded = p.sessions.filter((s) => s.result);
  const avg = graded.length ? Math.round(graded.reduce((n, s) => n + (s.result?.totalScore ?? 0), 0) / graded.length) : null;
  const flagged = p.sessions.reduce((n, s) => n + (s.result?.flags.length ?? 0), 0);
  const nodeOf = (key: string) => nodes.find((n) => n.key === key);
  const misconceptions = [...new Set(p.sessions.flatMap((s) => s.result?.detectedMisconceptions ?? []))];
  const latest = p.sessions[0];
  return (
    <>
      <header className="flex flex-wrap items-center gap-4">
        <span aria-hidden className="flex size-14 items-center justify-center rounded-full bg-teal-soft text-h2 font-bold text-teal">
          {initials(p.fullName)}
        </span>
        <div className="flex-1">
          <h1 className="text-h1 font-bold">{p.fullName}</h1>
          <p className="text-body-m text-ink-500">{p.studentCode}</p>
        </div>
        {latest && (
          <Link to={`/gv/sessions/${latest.sessionId}?classId=${classId}&studentId=${p.studentId}`} className="rounded-md bg-honey px-4 py-2 font-semibold text-ink-900">
            Xem transcript
          </Link>
        )}
      </header>

      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Tiến độ" value={`${p.masteredCount}/${p.totalCount}`} note="nút đã Đạt" />
        <Stat label="Số phiên" value={p.sessions.length} note="đã giảng" />
        <Stat label="Điểm trung bình" value={avg ?? "–"} note="trên thang 100" />
        <Stat label="Cờ vi phạm" value={flagged} note="lượt bị gắn cờ" />
      </dl>

      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        <section aria-label="Trạng thái từng nút" className="space-y-2 rounded-lg border border-line-soft bg-surface p-4">
          <h2 className="text-h3 font-semibold">Trạng thái từng nút</h2>
          <div className="overflow-x-auto">
            <table className="min-w-full text-body-m">
              <thead>
                <tr className="text-left text-body-s text-ink-500">
                  <th className="py-2 pr-3 font-semibold">Mã</th>
                  <th className="py-2 pr-3 font-semibold">Tên nút</th>
                  <th className="py-2 pr-3 font-semibold">Trạng thái</th>
                  <th className="py-2 pr-3 text-right font-semibold">Cao nhất</th>
                  <th className="py-2 text-right font-semibold">Lượt</th>
                </tr>
              </thead>
              <tbody>
                {p.progress.map((n) => {
                  const look = MASTERY[n.state as MasteryState];
                  const Icon = look.icon;
                  const node = nodeOf(n.nodeKey);
                  return (
                    <tr key={n.nodeKey} className="border-t border-line-soft">
                      <td className="py-2 pr-3 text-body-s text-ink-500">{node?.code ?? n.nodeKey}</td>
                      <td className="py-2 pr-3 font-semibold">{node?.title ?? n.nodeKey}</td>
                      <td className="py-2 pr-3">
                        <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-body-s font-semibold ${look.className}`}>
                          <Icon aria-hidden size={12} /> {look.label}
                        </span>
                      </td>
                      <td className="py-2 pr-3 text-right font-bold">{n.bestScore == null ? "–" : Math.round(n.bestScore)}</td>
                      <td className="py-2 text-right">{n.attempts}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <div className="space-y-4">
          <section aria-label="Lịch sử phiên" className="space-y-2 rounded-lg border border-line-soft bg-surface p-4">
            <h2 className="flex justify-between text-h3 font-semibold">
              Lịch sử phiên <span className="text-body-s font-normal text-ink-500">{p.sessions.length} phiên</span>
            </h2>
            {p.sessions.length === 0 && <p className="text-body-m text-ink-500">Sinh viên chưa giảng phiên nào.</p>}
            <ul className="divide-y divide-line-soft">
              {p.sessions.map((s) => {
                const passed = s.result?.verdict === "PASSED";
                return (
                  <li key={s.sessionId} className="py-2">
                    <Link to={`/gv/sessions/${s.sessionId}?classId=${classId}&studentId=${p.studentId}`} className="flex items-center justify-between gap-2 hover:text-teal">
                      <span>
                        <span className="block font-semibold">{s.nodeTitle ?? s.nodeKey}</span>
                        <span className="block text-body-s text-ink-500">{vn(s.startedAt)}</span>
                      </span>
                      {s.result ? (
                        <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-body-s font-semibold ${passed ? "bg-st-pass text-green-900" : "bg-st-fail text-red-900"}`}>
                          {passed ? "✓ Đạt" : "✗ Chưa đạt"} · {Math.round(s.result.totalScore)}
                        </span>
                      ) : (
                        <span className="text-body-s text-ink-500">{s.status}</span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </section>
          <section aria-label="Quan niệm sai còn tồn tại" className="space-y-2 rounded-lg border border-line-soft bg-surface p-4">
            <h2 className="text-h3 font-semibold">Quan niệm sai còn tồn tại</h2>
            {misconceptions.length === 0 && <p className="text-body-m text-ink-500">Chưa phát hiện quan niệm sai nào.</p>}
            {misconceptions.map((m) => (
              <p key={m} className="rounded-md bg-st-fail px-3 py-2 text-body-m text-red-900">
                ✗ {m}
              </p>
            ))}
          </section>
        </div>
      </div>
    </>
  );
}

function Stat({ label, value, note }: { label: string; value: string | number; note: string }) {
  return (
    <div className="rounded-lg border border-line-soft bg-surface p-4">
      <dt className="caps">{label}</dt>
      <dd className="text-h1 font-bold">{value}</dd>
      <p className="text-body-s text-ink-500">{note}</p>
    </div>
  );
}
