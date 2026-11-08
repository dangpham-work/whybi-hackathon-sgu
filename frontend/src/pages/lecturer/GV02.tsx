import { Archive, ArchiveRestore, Flame, Network, Pencil, Upload } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { AsyncView, EmptyBox } from "../../components/AsyncView";
import { CopyCode } from "../../components/CopyCode";
import { apiCall, ApiError, errorText } from "../../lib/api";
import { useMyClasses } from "../../lib/classes";
import { NO_TREE, TREE_STATUS } from "../../lib/status";
import { useApi } from "../../lib/useApi";

/** GV-02 Tổng quan lớp (Figma 14:1122, FR-SK-01, GD-05): thông tin lớp + phiên bản cây hiện hành. */
export default function LecturerClassOverview() {
  const { classId = "" } = useParams();
  const classes = useMyClasses();
  const [archivedOverride, setArchivedOverride] = useState<boolean | null>(null);

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
                          <p className="text-body-m text-ink-500">
                            {isArchived
                              ? "Lớp chưa có cây kỹ năng trước khi lưu trữ."
                              : "Tải giáo trình để Whybi AI sinh cây kỹ năng tự động."}
                          </p>
                          {!isArchived && (
                            <Link to={`${base}/syllabus`} className="inline-flex items-center gap-2 rounded-md bg-honey px-4 py-2 font-semibold">
                              <Upload aria-hidden size={16} /> Tải giáo trình
                            </Link>
                          )}
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
                          <Link to={`${base}/heatmap`} className="inline-flex items-center gap-2 rounded-md bg-teal px-4 py-2 font-semibold text-white">
                            <Flame aria-hidden size={16} /> Mở bản đồ nhiệt
                          </Link>
                          {!isArchived && (
                            <>
                              <Link to={`${base}/tree`} className="inline-flex items-center gap-2 rounded-md border border-line-strong px-4 py-2 font-semibold">
                                <Pencil aria-hidden size={16} /> Mở trình sửa
                              </Link>
                              <Link to={`${base}/syllabus`} className="inline-flex items-center gap-2 rounded-md border border-line-strong px-4 py-2 font-semibold">
                                <Network aria-hidden size={16} /> Tải giáo trình mới
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

function Fact({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="caps">{label}</dt>
      <dd className="text-h3 font-bold">{value}</dd>
    </div>
  );
}
