import { Download, EyeOff, Flame, Maximize2, Mic, Search, TriangleAlert, Users, Wifi, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { AsyncView } from "../../components/AsyncView";
import { HeatGrid } from "../../components/HeatGrid";
import { NodeDetailDrawer } from "../../components/NodeDetailDrawer";
import { SkillTree } from "../../components/SkillTree";
import { StatsTab } from "../../components/stats/StatsTab";
import { apiCall, errorText } from "../../lib/api";
import { downloadFile } from "../../lib/download";
import { applyHeatmapEvent, detailsByKey, heatByKey, rootCauseKey, type Snapshot } from "../../lib/heatmap";
import { useApi } from "../../lib/useApi";
import { useChannel, type WsStatus } from "../../lib/ws";

type Tab = "tree" | "grid" | "heatmap" | "stats";

/** GV-05 Dashboard bản đồ nhiệt (Figma 17:1447, FR-HM-01…06, GD-10). Ảnh chụp + kênh `class:{id}:heatmap`, không cần tải lại trang. */
export default function LecturerHeatmap() {
  const { classId = "" } = useParams();
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [hideNames, setHideNames] = useState(false);
  const [present, setPresent] = useState(false);
  const anonymize = hideNames || present; // trình chiếu luôn ẩn tên (FR-HM-09)
  useEffect(() => {
    const t = setTimeout(() => setQ(search.trim()), 300); // chờ gõ xong rồi mới lọc
    return () => clearTimeout(t);
  }, [search]);

  // Lọc và ẩn tên do máy chủ làm: tên SV không bao giờ tới trình duyệt khi đang trình chiếu
  const snap = useApi(
    (signal) => apiCall("get", "/classes/{class_id}/heatmap", { path: { class_id: classId }, query: { q: q || undefined, anonymize }, signal }),
    [classId, q, anonymize],
  );
  const [live, setLive] = useState<Snapshot>();
  useEffect(() => setLive(snap.data), [snap.data]);

  const status = useChannel(`class:${classId}:heatmap`, (e) => {
    if (e.event === "reconnected") snap.reload(); // mất kết nối thì dữ liệu có thể đã lỡ – lấy lại ảnh chụp (UC10 E1)
    else setLive((s) => (s ? applyHeatmapEvent(s, e, anonymize) : s));
  });

  const body = (
    <div className={`space-y-5 ${present ? "p-6" : "p-4 lg:p-7"}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-h1 font-bold">Bản đồ nhiệt lớp học</h1>
        <Toolbar classId={classId} search={search} onSearch={setSearch} hideNames={anonymize} lockHide={present} onHide={setHideNames} present={present} onPresent={setPresent} />
      </div>
      <AsyncView state={snap.status === "success" && live ? { ...snap, data: live } : snap} loadingText="Đang tải bản đồ nhiệt…">
        {(s) => <Dashboard s={s} classId={classId} wsStatus={status} hideNames={anonymize} />}
      </AsyncView>
    </div>
  );
  return present ? <div role="dialog" aria-label="Chế độ trình chiếu" className="fixed inset-0 z-50 overflow-auto bg-app">{body}</div> : body;
}

const WS_TEXT: Partial<Record<WsStatus, string>> = { reconnecting: "Mất kết nối – đang nối lại…", connecting: "Đang kết nối…", closed: "Mất kết nối" };

/** Tìm theo tên / MSSV, ẩn tên khi chiếu, trình chiếu toàn màn hình, xuất báo cáo (FR-HM-09, 10; GD-14, GD-16). */
function Toolbar(p: { classId: string; search: string; onSearch: (v: string) => void; hideNames: boolean; lockHide: boolean; onHide: (v: boolean) => void; present: boolean; onPresent: (v: boolean) => void }) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string>();
  async function exportAs(format: "csv" | "pdf") {
    setBusy(true);
    setFailure(undefined);
    try {
      await downloadFile(`/classes/${p.classId}/report?format=${format}`, `bao-cao-lop.${format}`);
    } catch (e) {
      setFailure(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  const btn = "inline-flex items-center gap-1 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-body-s font-semibold disabled:opacity-50";
  return (
    <div className="flex flex-wrap items-center gap-2">
      {!p.present && (
        <label className="flex items-center gap-1 rounded-md border border-line-strong bg-surface px-2 py-1.5">
          <Search aria-hidden size={14} />
          <input aria-label="Tìm sinh viên theo tên hoặc MSSV" placeholder="Tìm tên / MSSV" value={p.search} onChange={(e) => p.onSearch(e.target.value)} className="w-40 bg-transparent text-body-s outline-none" />
        </label>
      )}
      <button type="button" aria-pressed={p.hideNames} disabled={p.lockHide} onClick={() => p.onHide(!p.hideNames)} className={btn}>
        <EyeOff aria-hidden size={14} /> Ẩn tên khi chiếu
      </button>
      {p.present ? (
        <button type="button" onClick={() => p.onPresent(false)} className={btn}>
          <X aria-hidden size={14} /> Thoát trình chiếu
        </button>
      ) : (
        <>
          <button type="button" onClick={() => p.onPresent(true)} className={btn}>
            <Maximize2 aria-hidden size={14} /> Trình chiếu
          </button>
          <button type="button" disabled={busy} onClick={() => exportAs("csv")} className={btn}>
            <Download aria-hidden size={14} /> Xuất CSV
          </button>
          <button type="button" disabled={busy} onClick={() => exportAs("pdf")} className={btn}>
            <Download aria-hidden size={14} /> Xuất PDF
          </button>
        </>
      )}
      {failure && <p role="alert" className="w-full text-body-s text-red-800">{failure}</p>}
    </div>
  );
}

function Dashboard({ s, classId, wsStatus, hideNames }: { s: Snapshot; classId: string; wsStatus: WsStatus; hideNames: boolean }) {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [tab, setTabState] = useState<Tab>(
    params.get("tab") === "thong-ke"
      ? "stats"
      : params.get("tab") === "ban-do-nhiet"
      ? "heatmap"
      : params.get("tab") === "ma-tran"
      ? "grid"
      : "tree",
  );
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const setTab = (t: Tab) => {
    setTabState(t);
    const p = new URLSearchParams(params);
    if (t === "stats") p.set("tab", "thong-ke");
    else if (t === "heatmap") p.set("tab", "ban-do-nhiet");
    else if (t === "grid") p.set("tab", "ma-tran");
    else p.delete("tab");
    setParams(p, { replace: true });
  };
  const alerts = s.alerts ?? [];
  const goNode = (nodeId?: string | null) => nodeId && navigate(`/gv/classes/${classId}/nodes/${nodeId}`);

  return (
    <div className="space-y-4">
      <p className="flex flex-wrap items-center gap-x-5 gap-y-1 text-body-m">
        <span className="flex items-center gap-1">
          <Users aria-hidden size={16} /> Sĩ số <strong>{s.enrolledCount}</strong>
        </span>
        <span className="flex items-center gap-1">
          <Wifi aria-hidden size={16} className="text-teal" /> Trực tuyến <strong>{s.onlineCount}</strong>
        </span>
        <span className="flex items-center gap-1">
          <Mic aria-hidden size={16} className="text-honey-deep" /> Phiên đang diễn ra <strong>{s.activeSessions}</strong>
        </span>
        {WS_TEXT[wsStatus] && (
          <span role="status" className="flex items-center gap-1 text-honey-deep">
            <TriangleAlert aria-hidden size={14} /> {WS_TEXT[wsStatus]}
          </span>
        )}
      </p>

      {/* 4 Tabs theo đặc tả MX3 */}
      <div role="tablist" aria-label="Chế độ xem" className="inline-flex flex-wrap gap-1 rounded-lg bg-app p-1">
        {(
          [
            ["tree", "Tiến độ học theo cây", "Chế độ cây"],
            ["grid", "Theo ma trận", "Lưới SV × Nút"],
            ["heatmap", "Theo bản đồ nhiệt", "Theo bản đồ nhiệt"],
            ["stats", "Theo thống kê", "Thống kê"],
          ] as const
        ).map(([id, label, ariaLabel]) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            aria-label={ariaLabel}
            onClick={() => setTab(id)}
            className={`rounded-md px-4 py-1.5 text-body-m font-semibold transition-all ${
              tab === id ? "bg-surface shadow-card text-ink-900" : "text-ink-500 hover:text-ink-900"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Tab 1: Cây kỹ năng (Toàn màn hình mặc định, click nút mở trượt chi tiết bên trái) */}
      {tab === "tree" && (
        <div className="space-y-3">
          {/* Cảnh báo điểm nghẽn gọn gàng */}
          <aside aria-label="Cảnh báo điểm nghẽn">
            {alerts.length === 0 ? (
              <p className="rounded-lg border border-dashed border-line-strong bg-surface/50 px-4 py-2 text-body-s text-ink-500">
                Chưa có điểm nghẽn nào – lớp đang tiến triển ổn.
              </p>
            ) : (
              <div className="space-y-2">
                {alerts.map((a) => (
                  <div
                    key={a.nodeId}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-700/40 bg-st-fail/25 px-4 py-2.5"
                  >
                    <div className="space-y-0.5">
                      <p className="flex items-center gap-2 text-body-m font-bold text-red-900">
                        <TriangleAlert aria-hidden size={16} className="text-red-700 shrink-0" />
                        {a.message}
                      </p>
                      {a.conditionalFailRate != null && (
                        <p className="text-body-xs text-ink-700 pl-6">
                          {Math.round(a.conditionalFailRate * 100)}% SV trượt nút này cũng chưa Đạt nút gốc
                          {a.failedCount != null && ` (${a.failedCount} SV)`}.
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setSelectedNodeId(a.rootCauseNodeId)}
                        className="rounded-md border border-red-700/50 bg-surface px-3 py-1 text-body-s font-semibold text-red-900 hover:bg-red-50"
                      >
                        Xem chi tiết nút gốc
                      </button>
                      <Link
                        to={`/gv/classes/${classId}/matching`}
                        className="rounded-md border border-line-strong bg-surface px-3 py-1 text-body-s font-semibold hover:bg-app"
                      >
                        Ghép cặp ưu tiên
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </aside>

          {/* Vùng cây: Mặc định chiếm 100% window, khi chọn nút thì bên trái trượt mở chi tiết */}
          <div className="relative flex flex-col lg:flex-row gap-4 items-stretch w-full min-h-[580px]">
            {selectedNodeId && (
              <aside
                aria-label="Chi tiết nút kỹ năng"
                className="w-full lg:w-[400px] shrink-0 rounded-lg border border-line-soft bg-surface p-4 shadow-sm overflow-y-auto max-h-[calc(100vh-250px)] transition-all duration-300 ease-in-out"
              >
                <NodeDetailDrawer
                  classId={classId}
                  nodeId={selectedNodeId}
                  initialStat={s.nodes.find((n) => n.nodeId === selectedNodeId)}
                  onClose={() => setSelectedNodeId(null)}
                  hideNames={hideNames}
                  onSelectNode={(id) => setSelectedNodeId(id)}
                />
              </aside>
            )}

            <section
              aria-label="Cây kỹ năng theo tỉ lệ Đạt"
              className="flex-1 min-w-0 rounded-lg border border-line-soft bg-surface p-4 transition-all duration-300 ease-in-out"
            >
              {s.tree ? (
                <SkillTree
                  mode="heatmap"
                  nodes={s.tree.nodes}
                  edges={s.tree.edges}
                  heat={heatByKey(s)}
                  details={detailsByKey(s)}
                  rootCauseKey={rootCauseKey(s)}
                  selectedKey={s.tree.nodes.find((n) => n.id === selectedNodeId)?.key ?? null}
                  height={560}
                  onNodeClick={(n) => setSelectedNodeId(n.id === selectedNodeId ? null : (n.id ?? null))}
                />
              ) : (
                <p className="text-body-m text-ink-500">Lớp chưa có cây đang phát hành.</p>
              )}
            </section>
          </div>
        </div>
      )}

      {/* Tab 2: Ma trận thành thạo (Khung lớn chiếm trọn, thanh cuộn riêng, freeze panes như Excel) */}
      {tab === "grid" && (
        <section aria-label="Ma trận thành thạo" className="w-full">
          <HeatGrid rows={s.grid} nodes={s.nodes} classId={classId} hideNames={hideNames} />
        </section>
      )}

      {/* Tab 3: Bản đồ nhiệt realtime */}
      {tab === "heatmap" && (
        <section
          aria-label="Bản đồ nhiệt realtime"
          className="rounded-lg border border-dashed border-line-strong bg-surface p-12 text-center space-y-3"
        >
          <Flame className="mx-auto text-honey-deep" size={40} />
          <h3 className="text-h3 font-bold text-ink-900">Theo bản đồ nhiệt</h3>
          <p className="text-body-m text-ink-500 max-w-md mx-auto">
            Hiện đang có <strong>{s.activeSessions}</strong> phiên giảng đang diễn ra. Chức năng đang được chuẩn bị theo
            thiết kế mới.
          </p>
        </section>
      )}

      {/* Tab 4: Thống kê (Giữ nguyên) */}
      {tab === "stats" && (
        <div className="w-full">
          <StatsTab s={s} classId={classId} hideNames={hideNames} />
        </div>
      )}
    </div>
  );
}
