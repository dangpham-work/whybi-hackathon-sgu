import { Flame, Network, Pencil, Upload } from "lucide-react";
import { Link, useParams } from "react-router";
import { AsyncView, EmptyBox } from "../../components/AsyncView";
import { CopyCode } from "../../components/CopyCode";
import { apiCall, ApiError } from "../../lib/api";
import { useMyClasses } from "../../lib/classes";
import { NO_TREE, TREE_STATUS } from "../../lib/status";
import { useApi } from "../../lib/useApi";

/** GV-02 Tổng quan lớp (Figma 14:1122, FR-SK-01, GD-05): thông tin lớp + phiên bản cây hiện hành. */
export default function LecturerClassOverview() {
  const { classId = "" } = useParams();
  const classes = useMyClasses();
  // 404 = lớp chưa có cây → coi là "chưa có", không phải lỗi
  const tree = useApi(
    (signal) =>
      apiCall("get", "/classes/{class_id}/tree", { path: { class_id: classId }, signal }).catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }),
    [classId],
  );
  const base = `/gv/classes/${classId}`;
  return (
    <div className="space-y-6 p-4 lg:p-7">
      <AsyncView state={classes} loadingText="Đang tải lớp…">
        {(list) => {
          const c = list.find((x) => x.id === classId);
          if (!c) return <EmptyBox>Không tìm thấy lớp này trong danh sách lớp bạn phụ trách.</EmptyBox>;
          return (
            <>
              <header className="space-y-2">
                <h1 className="text-h1 font-bold">{c.name}</h1>
                <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-body-m text-ink-500">
                  <span>{c.semester}</span>
                  <span>{c.studentCount} sinh viên</span>
                  <span className="flex items-center gap-2">
                    Mã tham gia <CopyCode code={c.joinCode} />
                  </span>
                </p>
              </header>
              <section aria-label="Cây kỹ năng" className="space-y-4 rounded-lg border border-line-soft bg-surface p-5">
                <h2 className="text-h3 font-semibold">Cây kỹ năng</h2>
                <AsyncView state={tree} loadingText="Đang tải cây kỹ năng…">
                  {(t) => {
                    if (!t)
                      return (
                        <div className="space-y-3">
                          <p className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-body-s font-semibold ${NO_TREE.className}`}>
                            <NO_TREE.icon aria-hidden size={14} /> {NO_TREE.label}
                          </p>
                          <p className="text-body-m text-ink-500">Tải giáo trình để Whybi AI sinh cây kỹ năng tự động.</p>
                          <Link to={`${base}/syllabus`} className="inline-flex items-center gap-2 rounded-md bg-honey px-4 py-2 font-semibold">
                            <Upload aria-hidden size={16} /> Tải giáo trình
                          </Link>
                        </div>
                      );
                    const look = TREE_STATUS[t.status] ?? NO_TREE;
                    return (
                      <div className="space-y-4">
                        <dl className="grid grid-cols-2 gap-3 text-body-m sm:grid-cols-4">
                          <Fact label="Phiên bản" value={`v${t.versionNo}`} />
                          <Fact label="Số nút" value={t.nodes.length} />
                          <Fact label="Số cạnh" value={t.edges.length} />
                          <div>
                            <dt className="caps">Trạng thái</dt>
                            <dd className={`mt-1 inline-flex items-center gap-1 rounded-md border px-2 py-1 text-body-s font-semibold ${look.className}`}>
                              <look.icon aria-hidden size={14} /> {look.label}
                            </dd>
                          </div>
                        </dl>
                        <div className="flex flex-wrap gap-2">
                          <Link to={`${base}/tree`} className="inline-flex items-center gap-2 rounded-md border border-line-strong px-4 py-2 font-semibold">
                            <Pencil aria-hidden size={16} /> Mở trình sửa
                          </Link>
                          <Link to={`${base}/heatmap`} className="inline-flex items-center gap-2 rounded-md bg-teal px-4 py-2 font-semibold text-white">
                            <Flame aria-hidden size={16} /> Mở bản đồ nhiệt
                          </Link>
                          <Link to={`${base}/syllabus`} className="inline-flex items-center gap-2 rounded-md border border-line-strong px-4 py-2 font-semibold">
                            <Network aria-hidden size={16} /> Tải giáo trình mới
                          </Link>
                        </div>
                      </div>
                    );
                  }}
                </AsyncView>
              </section>
            </>
          );
        }}
      </AsyncView>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="caps">{label}</dt>
      <dd className="text-h3 font-bold">{value}</dd>
    </div>
  );
}
