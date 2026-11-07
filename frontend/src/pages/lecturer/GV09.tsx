import { CircleCheck, Info, Pencil, Play, Users } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router";
import { AsyncView, ErrorBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { apiCall, errorText, type Schema } from "../../lib/api";
import { isActive, MATCH_STATUS, percent, type MatchOut } from "../../lib/matching";
import { useApi } from "../../lib/useApi";

/** GV-09 Quản lý ghép cặp (Figma 19:2649, FR-PM-01, 02, GD-11): chạy vòng, danh sách cặp, thống kê. Điều chỉnh thủ công: GD-12. */
export default function LecturerMatching() {
  const { classId = "" } = useParams();
  const matches = useApi((signal) => apiCall("get", "/classes/{class_id}/matches", { path: { class_id: classId }, signal }), [classId]);
  const stats = useApi((signal) => apiCall("get", "/classes/{class_id}/matching-stats", { path: { class_id: classId }, signal }), [classId]);
  const tree = useApi((signal) => apiCall("get", "/classes/{class_id}/tree", { path: { class_id: classId }, signal }), [classId]);
  const [priority, setPriority] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>();
  const [last, setLast] = useState<Schema<"RoundOut">>();
  // Danh sách SV của lớp để chọn người thay thế khi điều chỉnh cặp (lấy từ lưới bản đồ nhiệt, chỉ GV phụ trách xem được)
  const students = useApi((signal) => apiCall("get", "/classes/{class_id}/heatmap", { path: { class_id: classId }, signal }).then((h) => h.grid), [classId]);
  const title = (key: string) => tree.data?.nodes.find((n) => n.key === key)?.title ?? key;
  const code = (key: string) => tree.data?.nodes.find((n) => n.key === key)?.code ?? key;

  async function run() {
    setBusy(true);
    setFailure(undefined);
    try {
      const round = await apiCall("post", "/classes/{class_id}/matching-rounds", { path: { class_id: classId }, body: { priorityNodeId: priority || null } });
      setLast(round);
      matches.reload();
      stats.reload();
    } catch (e) {
      setFailure(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5 p-4 lg:p-7">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-h1 font-bold">Ghép cặp bạn cùng tiến</h1>
          <p className="text-body-m text-ink-500">Ghép cặp bù trừ hai chiều: hai bạn mỗi người dạy lại nút bạn kia chưa Đạt.</p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-body-s font-semibold">
            <span className="sr-only">Ưu tiên nút</span>
            <select value={priority} onChange={(e) => setPriority(e.target.value)} className="rounded-md border border-line-strong px-3 py-2 text-body-m">
              <option value="">Không ưu tiên nút nào</option>
              {tree.data?.nodes.map((n) => (
                <option key={n.id ?? n.key} value={n.id ?? ""}>
                  Ưu tiên {n.code ?? n.key} {n.title}
                </option>
              ))}
            </select>
          </label>
          <Button disabled={busy} onClick={run}>
            <Play aria-hidden size={16} /> Chạy vòng ghép cặp
          </Button>
        </div>
      </header>

      {failure !== undefined && <ErrorBox text={failureText(failure)} />}
      {last && (
        <p role="status" className="flex items-center gap-2 rounded-lg bg-st-pass px-4 py-2 text-body-m text-green-900">
          <CircleCheck aria-hidden size={16} /> Đã ghép {last.matches.length} cặp từ {last.participantCount} SV
          {last.waitingStudentIds.length > 0 && `; ${last.waitingStudentIds.length} SV chờ vòng sau`}.
        </p>
      )}

      <AsyncView state={stats}>
        {(s) => (
          <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Tổng số cặp" value={s.totalMatches} note={`${s.declined} từ chối · ${s.expired} hết hạn`} />
            <Stat label="Tỉ lệ chấp nhận" value={percent(s.acceptRate)} note={`${s.accepted}/${s.totalMatches} cặp hai bên đồng ý`} />
            <Stat label="Đã học cùng" value={s.studied} note={`${percent(s.studiedRate)} số cặp đã chấp nhận`} />
            <Stat label="Xác nhận lại Đạt" value={s.itemsVerified} note={`${percent(s.verifiedRate)} mục dạy–học (${s.itemsTotal})`} />
          </dl>
        )}
      </AsyncView>

      <section aria-label="Danh sách cặp" className="space-y-3 rounded-lg border border-line-soft bg-surface p-4">
        <h2 className="text-h3 font-semibold">Danh sách cặp</h2>
        <AsyncView state={matches} isEmpty={(l) => l.length === 0} empty="Chưa có cặp nào. Bấm “Chạy vòng ghép cặp” khi đã có ít nhất 2 SV bật ghép cặp.">
          {(list) => (
            <div className="overflow-x-auto">
              <table className="min-w-full text-body-m">
                <thead>
                  <tr className="text-left text-body-s text-ink-500">
                    <th className="py-2 pr-3 font-semibold">Sinh viên A</th>
                    <th className="py-2 pr-3 font-semibold">Sinh viên B</th>
                    <th className="py-2 pr-3 font-semibold">A dạy B</th>
                    <th className="py-2 pr-3 font-semibold">B dạy A</th>
                    <th className="py-2 pr-3 font-semibold">Trọng số</th>
                    <th className="py-2 pr-3 font-semibold">Trạng thái</th>
                    <th className="py-2 font-semibold">Điều chỉnh</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((m) => (
                    <Row key={m.id} m={m} code={code} title={title} students={students.data ?? []} onChanged={() => { matches.reload(); stats.reload(); }} />
                  ))}
                </tbody>
              </table>
              <p className="pt-2 text-body-s text-ink-500">
                {list.filter((m) => isActive(m.status)).length} cặp đang hoạt động / {list.length} cặp
              </p>
            </div>
          )}
        </AsyncView>
        <p className="flex items-center gap-2 text-body-s text-ink-500">
          <Info aria-hidden size={14} /> Không ghép lại cùng cặp trong 14 ngày (BR-08).
        </p>
      </section>
    </div>
  );
}

/** Mã lỗi riêng của vòng ghép cặp (matching.py) – chưa nằm trong FRIENDLY chung. */
const ADJUST_ERR: Record<string, string> = {
  MATCH_INVALID_STATE: "Cặp này đã kết thúc nên không điều chỉnh được.",
  REPLACE_NOT_IN_MATCH: "Sinh viên được thay không thuộc cặp này.",
  STUDENT_NOT_IN_CLASS: "Sinh viên được chọn không thuộc lớp.",
  STUDENT_NOT_OPTED_IN: "Sinh viên được chọn đã tắt tham gia ghép cặp.",
  STUDENT_BUSY: "Sinh viên được chọn đang trong một cặp hoạt động khác.",
  NO_COMPLEMENTARY_NODES: "Hai sinh viên này không có nút nào để dạy lẫn nhau.",
};
function failureText(e: unknown): string {
  const code = (e as { code?: string }).code;
  if (code && ADJUST_ERR[code]) return ADJUST_ERR[code];
  if (code === "NOT_ENOUGH_PARTICIPANTS") return "Chưa đủ 2 sinh viên bật ghép cặp để chạy vòng này.";
  if (code === "TREE_NOT_PUBLISHED") return "Lớp chưa phát hành cây kỹ năng nên chưa ghép cặp được.";
  return errorText(e);
}

function Row({ m, code, title, students, onChanged }: { m: MatchOut; code: (k: string) => string; title: (k: string) => string; students: Schema<"GridRow">[]; onChanged: () => void }) {
  const look = MATCH_STATUS[m.status];
  const Icon = look.icon;
  const [editing, setEditing] = useState(false);
  return (
    <>
      <RowCells m={m} code={code} title={title} look={look} Icon={Icon} onEdit={isActive(m.status) ? () => setEditing((e) => !e) : undefined} />
      {editing && (
        <tr>
          <td colSpan={7} className="bg-app p-3">
            <Adjust m={m} students={students} onDone={() => { setEditing(false); onChanged(); }} />
          </td>
        </tr>
      )}
    </>
  );
}

/** Điều chỉnh cặp thủ công (FR-PM-08): hủy cặp, hoặc thay một SV bằng SV khác (cặp quay về chờ hai bên chấp nhận lại). */
function Adjust({ m, students, onDone }: { m: MatchOut; students: Schema<"GridRow">[]; onDone: () => void }) {
  const [replace, setReplace] = useState(m.studentAId);
  const [withId, setWithId] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>();
  const pair = [m.studentAId, m.studentBId];
  async function send(body: Schema<"MatchAdjust">) {
    setBusy(true);
    setFailure(undefined);
    try {
      await apiCall("patch", "/matches/{match_id}", { path: { match_id: m.id }, body });
      onDone();
    } catch (e) {
      setFailure(e);
      setBusy(false);
    }
  }
  return (
    <div className="space-y-2">
      {failure !== undefined && <ErrorBox text={failureText(failure)} />}
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-body-s font-semibold">
          Thay
          <select aria-label="Sinh viên được thay" className="ml-2 rounded-md border border-line-strong px-2 py-1.5" value={replace} onChange={(e) => setReplace(e.target.value)}>
            <option value={m.studentAId}>{m.studentAName}</option>
            <option value={m.studentBId}>{m.studentBName}</option>
          </select>
        </label>
        <label className="text-body-s font-semibold">
          bằng
          <select aria-label="Sinh viên thay thế" className="ml-2 rounded-md border border-line-strong px-2 py-1.5" value={withId} onChange={(e) => setWithId(e.target.value)}>
            <option value="">Chọn sinh viên…</option>
            {students.filter((s) => !pair.includes(s.studentId)).map((s) => (
              <option key={s.studentId} value={s.studentId}>{s.studentName}</option>
            ))}
          </select>
        </label>
        <Button disabled={busy || !withId} onClick={() => send({ cancel: false, replaceStudentId: replace, withStudentId: withId })}>Thay sinh viên</Button>
        <Button variant="danger" disabled={busy} onClick={() => send({ cancel: true })}>Hủy cặp</Button>
      </div>
    </div>
  );
}

function RowCells({ m, code, title, look, Icon, onEdit }: { m: MatchOut; code: (k: string) => string; title: (k: string) => string; look: (typeof MATCH_STATUS)[MatchOut["status"]]; Icon: (typeof MATCH_STATUS)[MatchOut["status"]]["icon"]; onEdit?: () => void }) {
  return (
    <tr className="border-t border-line-soft">
      <td className="py-2 pr-3 font-semibold">{m.studentAName}</td>
      <td className="py-2 pr-3 font-semibold">{m.studentBName}</td>
      <td className="py-2 pr-3">
        <Chips keys={m.iTeach} code={code} title={title} />
      </td>
      <td className="py-2 pr-3">
        <Chips keys={m.iLearn} code={code} title={title} />
      </td>
      <td className="py-2 pr-3 font-semibold">{m.weight.toFixed(1).replace(".", ",")}</td>
      <td className="py-2 pr-3">
        <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-body-s font-semibold ${look.className}`}>
          <Icon aria-hidden size={12} /> {look.label}
        </span>
      </td>
      <td className="py-2">
        {onEdit && (
          <button type="button" onClick={onEdit} aria-label={`Điều chỉnh cặp ${m.studentAName} và ${m.studentBName}`} className="rounded-md border border-line-strong p-1.5">
            <Pencil aria-hidden size={14} />
          </button>
        )}
      </td>
    </tr>
  );
}

function Chips({ keys, code, title }: { keys: string[]; code: (k: string) => string; title: (k: string) => string }) {
  return (
    <span className="flex flex-wrap gap-1">
      {keys.map((k) => (
        <span key={k} className="whitespace-nowrap rounded-md bg-honey-soft px-2 py-0.5 text-body-s font-semibold text-honey-deep">
          → {code(k)} {title(k)}
        </span>
      ))}
    </span>
  );
}

function Stat({ label, value, note }: { label: string; value: string | number; note: string }) {
  return (
    <div className="rounded-lg border border-line-soft bg-surface p-4">
      <dt className="caps flex items-center gap-1">
        <Users aria-hidden size={12} /> {label}
      </dt>
      <dd className="text-h1 font-bold">{value}</dd>
      <p className="text-body-s text-ink-500">{note}</p>
    </div>
  );
}
