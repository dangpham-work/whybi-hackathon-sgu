import { CircleCheck, Flame, Network, Pencil, Plus, Upload, Users, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { AsyncView, DevelopingBox, ErrorBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { CopyCode } from "../../components/CopyCode";
import { ApiError, apiCall, errorText } from "../../lib/api";
import { useMyClasses, type ClassOut } from "../../lib/classes";
import { NO_TREE, TREE_STATUS } from "../../lib/status";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** GV-01 Danh sách lớp (Figma 14:699, FR-SK-01, GD-05). Số liệu tổng hợp tính từ danh sách lớp + tạo lớp học phần. */
export default function LecturerClasses() {
  const classes = useMyClasses();
  const [created, setCreated] = useState<ClassOut[]>([]);
  const [formOpen, setFormOpen] = useState(false);
  const [lastCreated, setLastCreated] = useState<ClassOut>();

  const merge = (list: ClassOut[]) => [...created, ...list.filter((c) => !created.some((n) => n.id === c.id))];

  return (
    <div className="space-y-6 p-4 lg:p-7">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-h1 font-bold">Lớp của tôi</h1>
          <p className="text-body-m text-ink-500">Các lớp học phần bạn phụ trách – chia sẻ mã tham gia cho sinh viên, tải giáo trình để Whybi AI sinh cây kỹ năng.</p>
        </div>
        <Button onClick={() => setFormOpen((o) => !o)} aria-expanded={formOpen}>
          {formOpen ? <X aria-hidden size={18} /> : <Plus aria-hidden size={18} />}
          {formOpen ? "Đóng biểu mẫu" : "Tạo lớp học phần"}
        </Button>
      </header>

      {formOpen && (
        <CreateClassForm
          onCreated={(c) => {
            setCreated((list) => [c, ...list]);
            setLastCreated(c);
            setFormOpen(false);
          }}
        />
      )}

      {lastCreated && (
        <div role="status" aria-label="Kết quả tạo lớp" className="flex flex-wrap items-center gap-3 rounded-lg border border-teal/40 bg-teal-soft p-4 text-body-m text-teal">
          <CircleCheck aria-hidden size={18} className="shrink-0" />
          <p className="flex-1">
            Đã tạo lớp <strong>{lastCreated.name}</strong>. Gửi mã tham gia <strong className="tracking-widest">{lastCreated.joinCode}</strong> cho sinh viên.
          </p>
          <Link to={`/gv/classes/${lastCreated.id}/syllabus`} className="inline-flex items-center justify-center gap-2 rounded-md bg-teal px-4 py-2 font-semibold text-white hover:brightness-110">
            <Upload aria-hidden size={16} /> Tải giáo trình
          </Link>
        </div>
      )}

      <AsyncView
        state={classes}
        isEmpty={(list) => list.length === 0 && created.length === 0}
        empty="Bạn chưa có lớp học phần nào. Bấm “Tạo lớp học phần” để bắt đầu."
      >
        {(list) => {
          const all = merge(list);
          return (
            <>
              <dl className="grid grid-cols-2 gap-3 lg:grid-cols-3">
                <Stat label="Lớp đang dạy" value={all.length} note={`${all.filter((c) => !c.treeStatus).length} lớp chưa có cây kỹ năng`} />
                <Stat label="Tổng sinh viên" value={all.reduce((n, c) => n + c.studentCount, 0)} note={`trên ${all.length} lớp học phần`} />
                <Stat label="Cây đã phát hành" value={all.filter((c) => c.treeStatus === "PUBLISHED").length} note="sẵn sàng cho sinh viên học" />
              </dl>
              <ul aria-label="Lớp học phần" className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
                {all.map((c) => (
                  <li key={c.id}>
                    <ClassCard c={c} />
                  </li>
                ))}
              </ul>
            </>
          );
        }}
      </AsyncView>
    </div>
  );
}

function Stat({ label, value, note }: { label: string; value: number; note: string }) {
  return (
    <div className="rounded-lg border border-line-soft bg-surface p-4">
      <dt className="caps">{label}</dt>
      <dd className="text-h1 font-bold">{value}</dd>
      <p className="text-body-s text-ink-500">{note}</p>
    </div>
  );
}

function ClassCard({ c }: { c: ClassOut }) {
  const look = (c.treeStatus && TREE_STATUS[c.treeStatus as keyof typeof TREE_STATUS]) || NO_TREE;
  const Icon = look.icon;
  const hasTree = look !== NO_TREE;
  const base = `/gv/classes/${c.id}`;
  return (
    <article className="space-y-4 rounded-lg border border-line-soft bg-surface p-5 shadow-card">
      <div className="flex items-center gap-3">
        <span aria-hidden className="flex size-10 items-center justify-center rounded-md bg-teal-soft text-teal">
          <Network size={20} />
        </span>
        <div className="min-w-0">
          <h2 className="truncate text-h3 font-semibold">
            <Link to={base} className="hover:text-teal">
              {c.name}
            </Link>
          </h2>
          <p className="flex items-center gap-1 text-body-s text-ink-500">
            <Users aria-hidden size={14} /> {c.semester} · {c.studentCount} sinh viên
          </p>
        </div>
      </div>
      <div className="flex items-center justify-between text-body-s text-ink-500">
        Mã tham gia <CopyCode code={c.joinCode} />
      </div>
      <p className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-body-s font-semibold ${look.className}`}>
        <Icon aria-hidden size={14} /> {hasTree ? `Cây kỹ năng · ${look.label}` : look.label}
      </p>
      <div className="grid grid-cols-2 gap-2">
        {hasTree ? (
          <>
            <Link to={`${base}/heatmap`} className="inline-flex items-center justify-center gap-2 rounded-md bg-teal px-4 py-2 font-semibold text-white">
              <Flame aria-hidden size={16} /> Bản đồ nhiệt
            </Link>
            <Link to={`${base}/tree`} className="inline-flex items-center justify-center gap-2 rounded-md border border-line-strong px-4 py-2 font-semibold">
              <Pencil aria-hidden size={16} /> Trình sửa cây
            </Link>
          </>
        ) : (
          <>
            <Link to={`${base}/syllabus`} className="inline-flex items-center justify-center gap-2 rounded-md bg-honey px-4 py-2 font-semibold text-ink-900">
              <Upload aria-hidden size={16} /> Tải giáo trình
            </Link>
            <Link to={base} className="inline-flex items-center justify-center rounded-md border border-line-strong px-4 py-2 font-semibold">
              Mở lớp
            </Link>
          </>
        )}
      </div>
    </article>
  );
}

function CreateClassForm({ onCreated }: { onCreated: (c: ClassOut) => void }) {
  const [courseId, setCourseId] = useState("");
  const [name, setName] = useState("");
  const [semester, setSemester] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>();

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    const body = { courseId: courseId.trim(), name: name.trim(), semester: semester.trim() };
    if (!UUID.test(body.courseId)) return setFailure("Mã môn học phải là mã định danh (UUID) quản trị viên cấp, vd. 8a0c2f7e-1d2b-4c3a-9e8f-7a6b5c4d3e2f.");
    setBusy(true);
    setFailure(undefined);
    try {
      onCreated(await apiCall("post", "/classes", { body }));
    } catch (err) {
      setFailure(err);
      setBusy(false);
    }
  }

  const field = "w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-body-m placeholder:text-ink-300 focus:outline-2 focus:outline-teal";
  return (
    <form aria-label="Tạo lớp học phần" onSubmit={submit} className="space-y-4 rounded-lg border border-honey/50 bg-honey-soft p-5">
      <h2 className="flex items-center gap-2 text-h3 font-semibold text-honey-deep">
        <Plus aria-hidden size={18} /> Tạo lớp học phần
      </h2>
      <div className="grid gap-4 md:grid-cols-3">
        <label className="space-y-1 text-body-s font-semibold text-ink-700">
          <span>Mã môn học</span>
          <input className={field} value={courseId} onChange={(e) => setCourseId(e.target.value)} required placeholder="UUID môn học" />
        </label>
        <label className="space-y-1 text-body-s font-semibold text-ink-700">
          <span>Tên lớp</span>
          <input className={field} value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} placeholder="CTDL&GT – Nhóm 02" />
        </label>
        <label className="space-y-1 text-body-s font-semibold text-ink-700">
          <span>Học kỳ</span>
          <input className={field} value={semester} onChange={(e) => setSemester(e.target.value)} required maxLength={20} placeholder="HK1 2026–2027" />
        </label>
      </div>
      {failure !== undefined &&
        (failure instanceof ApiError && failure.notImplemented ? (
          <DevelopingBox text={failure.message} />
        ) : (
          <ErrorBox text={typeof failure === "string" ? failure : errorText(failure)} />
        ))}
      <Button type="submit" disabled={busy}>
        <Plus aria-hidden size={16} /> {busy ? "Đang tạo…" : "Tạo lớp"}
      </Button>
    </form>
  );
}
