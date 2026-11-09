import {
  Archive,
  ArchiveRestore,
  Flame,
  GitFork,
  Layers,
  Network,
  Pencil,
  Sparkles,
  Upload,
  Users,
} from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { AsyncView, EmptyBox } from "../../components/AsyncView";
import { CopyCode } from "../../components/CopyCode";
import { apiCall, ApiError, errorText } from "../../lib/api";
import { useMyClasses } from "../../lib/classes";
import { NO_TREE, TREE_STATUS } from "../../lib/status";
import { useApi } from "../../lib/useApi";

/** GV-02 Tổng quan lớp (Figma 14:1122, FR-SK-01, GD-05): thông tin lớp + phiên bản cây hiện hành (kể cả bản nháp mới nhất). */
export default function LecturerClassOverview() {
  const { classId = "" } = useParams();
  const classes = useMyClasses();
  const [archivedOverride, setArchivedOverride] = useState<boolean | null>(null);

  // draft: true để lấy phiên bản mới nhất (kể cả bản nháp DRAFT chưa phát hành);
  // 404 = lớp chưa có cây nào → coi là "chưa có", hướng dẫn tải giáo trình
  const tree = useApi(
    (signal) =>
      apiCall("get", "/classes/{class_id}/tree", { path: { class_id: classId }, query: { draft: true }, signal }).catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }),
    [classId],
  );
  const base = `/gv/classes/${classId}`;

  async function toggleRestore(currentlyArchived: boolean) {
    try {
      const endpoint = currentlyArchived ? "/classes/{class_id}/restore" : "/classes/{class_id}/archive";
      await apiCall("post", endpoint as any, { path: { class_id: classId } });
      setArchivedOverride(!currentlyArchived);
    } catch (err) {
      alert(errorText(err));
    }
  }

  return (
    <div className="space-y-6 p-4 lg:p-7">
      <AsyncView state={classes} loadingText="Đang tải lớp…">
        {(list) => {
          const c = list.find((x) => x.id === classId);
          if (!c) return <EmptyBox>Không tìm thấy lớp này trong danh sách lớp bạn phụ trách.</EmptyBox>;
          const isArchived = archivedOverride !== null ? archivedOverride : c.status === "ARCHIVED";

          return (
            <>
              {isArchived && (
                <div role="status" aria-label="Cảnh báo lớp lưu trữ" className="flex items-center justify-between gap-3 rounded-lg border border-line-strong bg-honey-soft p-4 text-honey-deep">
                  <div className="flex items-center gap-3">
                    <Archive aria-hidden size={20} className="shrink-0" />
                    <p className="text-body-m">
                      Lớp học phần này đang trong <strong>Kho lưu trữ (Chỉ đọc)</strong>. Mọi thao tác tải giáo trình, sửa cây và ghép cặp đã bị khóa.
                    </p>
                  </div>
                  <button
                    onClick={() => toggleRestore(true)}
                    className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-body-s font-semibold text-ink-900 hover:bg-app"
                  >
                    <ArchiveRestore size={16} /> Khôi phục lớp
                  </button>
                </div>
              )}

              <header className="space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h1 className="text-h1 font-bold">{c.name}</h1>
                  {!isArchived && (
                    <button
                      onClick={() => toggleRestore(false)}
                      className="inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-body-s font-semibold text-ink-700 hover:bg-app"
                    >
                      <Archive size={16} /> Lưu trữ lớp
                    </button>
                  )}
                </div>
                <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-body-m text-ink-500">
                  <span>{c.semester}</span>
                  <span>{c.studentCount} sinh viên</span>
                  <span className="flex items-center gap-2">
                    {isArchived ? (
                      <span className="italic text-ink-400">Lớp đã đóng tham gia</span>
                    ) : (
                      <>
                        Mã tham gia <CopyCode code={c.joinCode} />
                      </>
                    )}
                  </span>
                </p>
              </header>
              <section aria-label="Cây kỹ năng" className="space-y-4 rounded-xl border border-line-soft bg-surface p-5 shadow-card">
                <div className="flex items-center justify-between border-b border-line-soft pb-3">
                  <h2 className="text-h3 font-semibold">Cây kỹ năng</h2>
                  <span className="text-body-s text-ink-500">Bản đồ kiến thức chuẩn hóa của học phần</span>
                </div>
                <AsyncView state={tree} loadingText="Đang tải cây kỹ năng…">
                  {(t) => {
                    if (!t)
                      return (
                        <div className="space-y-4 rounded-xl border border-dashed border-line-strong bg-app/40 p-6 text-center sm:text-left">
                          <div className="flex flex-col sm:flex-row items-center sm:items-start gap-4">
                            <div className="flex size-14 shrink-0 items-center justify-center rounded-2xl bg-honey-soft text-honey-deep shadow-inner">
                              <Sparkles size={28} />
                            </div>
                            <div className="space-y-1.5 flex-1">
                              <div className="flex flex-wrap items-center justify-center sm:justify-start gap-2">
                                <span className={`inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-body-s font-semibold ${NO_TREE.className}`}>
                                  <NO_TREE.icon aria-hidden size={14} /> {NO_TREE.label}
                                </span>
                              </div>
                              <p className="text-h3 font-bold text-ink-900">Khởi tạo cây kỹ năng cho lớp</p>
                              <p className="text-body-m text-ink-500 max-w-2xl">
                                {isArchived
                                  ? "Lớp chưa có cây kỹ năng trước khi lưu trữ."
                                  : "Tải giáo trình để Whybi AI sinh cây kỹ năng tự động."}
                              </p>
                            </div>
                          </div>
                          {!isArchived && (
                            <div className="pt-2 flex justify-center sm:justify-start">
                              <Link
                                to={`${base}/syllabus`}
                                className="inline-flex items-center gap-2 rounded-lg bg-honey px-5 py-2.5 font-bold text-ink-900 shadow-sm hover:brightness-105 transition-all text-body-m"
                              >
                                <Upload aria-hidden size={18} /> Tải giáo trình
                              </Link>
                            </div>
                          )}
                        </div>
                      );
                    const look = TREE_STATUS[t.status] ?? NO_TREE;
                    return (
                      <div className="space-y-5">
                        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                          <FactCard
                            icon={Layers}
                            label="Phiên bản"
                            value={`v${t.versionNo}`}
                            note="Phiên bản hiện hành"
                          />
                          <FactCard
                            icon={Network}
                            label="Số nút"
                            value={t.nodes.length}
                            note="Khái niệm & kỹ năng"
                          />
                          <FactCard
                            icon={GitFork}
                            label="Số cạnh"
                            value={t.edges.length}
                            note="Quan hệ tiên quyết"
                          />
                          <div className="rounded-xl border border-line-soft bg-app/50 p-4 transition-all hover:shadow-sm">
                            <dt className="caps text-ink-500">Trạng thái</dt>
                            <dd className="mt-2">
                              <span className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-body-s font-semibold shadow-sm ${look.className}`}>
                                <look.icon aria-hidden size={14} /> {look.label}
                              </span>
                            </dd>
                            <p className="mt-1 text-body-s text-ink-400">
                              {t.status === "PUBLISHED" ? "Sinh viên có thể học" : "Chờ duyệt & phát hành"}
                            </p>
                          </div>
                        </dl>
                        <div className="flex flex-wrap items-center gap-3 pt-1">
                          {t.status === "PUBLISHED" ? (
                            <Link
                              to={`${base}/heatmap`}
                              className="inline-flex items-center gap-2 rounded-lg bg-teal px-5 py-2.5 font-semibold text-white shadow-sm hover:brightness-110 transition-all text-body-m"
                            >
                              <Flame aria-hidden size={18} /> Mở bản đồ nhiệt
                            </Link>
                          ) : null}
                          {!isArchived && (
                            <>
                              <Link
                                to={`${base}/tree`}
                                className={`inline-flex items-center gap-2 rounded-lg px-4 py-2.5 font-semibold transition-all text-body-m ${
                                  t.status === "DRAFT"
                                    ? "bg-honey text-ink-900 shadow-sm hover:brightness-105"
                                    : "border border-line-strong bg-surface text-ink-900 hover:bg-app shadow-sm"
                                }`}
                              >
                                <Pencil aria-hidden size={18} /> {t.status === "DRAFT" ? "Tiếp tục chỉnh sửa cây" : "Xem / Sửa cây"}
                              </Link>
                              <Link
                                to={`${base}/matching`}
                                className="inline-flex items-center gap-2 rounded-lg border border-line-strong bg-surface px-4 py-2.5 font-semibold text-ink-900 hover:bg-app shadow-sm transition-all text-body-m"
                              >
                                <Users aria-hidden size={18} /> Ghép cặp
                              </Link>
                              <Link
                                to={`${base}/syllabus`}
                                className="inline-flex items-center gap-2 rounded-lg border border-line-strong bg-surface px-4 py-2.5 font-semibold text-ink-700 hover:bg-app shadow-sm transition-all text-body-m"
                              >
                                <Upload aria-hidden size={18} /> Tải giáo trình mới
                              </Link>
                            </>
                          )}
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

function FactCard({
  icon: Icon,
  label,
  value,
  note,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string;
  value: string | number;
  note: string;
}) {
  return (
    <div className="rounded-xl border border-line-soft bg-app/50 p-4 transition-all hover:shadow-sm">
      <div className="flex items-center justify-between">
        <dt className="caps text-ink-500">{label}</dt>
        <span className="flex size-7 items-center justify-center rounded-md bg-surface text-ink-500 shadow-xs">
          <Icon size={14} />
        </span>
      </div>
      <dd className="mt-1 text-h2 font-extrabold text-ink-900">{value}</dd>
      <p className="mt-0.5 text-body-s text-ink-400">{note}</p>
    </div>
  );
}
