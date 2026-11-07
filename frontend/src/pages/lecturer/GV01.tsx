import { Flame, Network, Pencil, Upload, Users } from "lucide-react";
import { Link } from "react-router";
import { AsyncView } from "../../components/AsyncView";
import { CopyCode } from "../../components/CopyCode";
import { useMyClasses, type ClassOut } from "../../lib/classes";
import { NO_TREE, TREE_STATUS } from "../../lib/status";

/** GV-01 Danh sách lớp (Figma 14:699, FR-SK-01, GD-05). Số liệu tổng hợp tính từ danh sách lớp. */
export default function LecturerClasses() {
  const classes = useMyClasses();
  return (
    <div className="space-y-6 p-4 lg:p-7">
      <header>
        <h1 className="text-h1 font-bold">Lớp của tôi</h1>
        <p className="text-body-m text-ink-500">Các lớp học phần bạn phụ trách.</p>
      </header>
      <AsyncView state={classes} isEmpty={(l) => l.length === 0} empty="Bạn chưa phụ trách lớp nào. Quản trị viên sẽ gán lớp cho bạn.">
        {(list) => (
          <>
            <dl className="grid grid-cols-2 gap-3 lg:grid-cols-3">
              <Stat label="Lớp đang dạy" value={list.length} note={`${list.filter((c) => !c.treeStatus).length} lớp chưa có cây kỹ năng`} />
              <Stat label="Tổng sinh viên" value={list.reduce((n, c) => n + c.studentCount, 0)} note={`trên ${list.length} lớp học phần`} />
              <Stat label="Cây đã phát hành" value={list.filter((c) => c.treeStatus === "PUBLISHED").length} note="sẵn sàng cho sinh viên học" />
            </dl>
            <ul aria-label="Lớp học phần" className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
              {list.map((c) => (
                <li key={c.id}>
                  <ClassCard c={c} />
                </li>
              ))}
            </ul>
          </>
        )}
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
