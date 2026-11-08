import { Download, EyeOff, Maximize2, Mic, Search, TriangleAlert, Users, Wifi, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { AsyncView } from "../../components/AsyncView";
import { HeatGrid } from "../../components/HeatGrid";
import { SkillTree } from "../../components/SkillTree";
import { StatsTab } from "../../components/stats/StatsTab";
import { apiCall, errorText } from "../../lib/api";
import { downloadFile } from "../../lib/download";
import { applyHeatmapEvent, detailsByKey, heatByKey, rootCauseKey, type Snapshot } from "../../lib/heatmap";
import { useApi } from "../../lib/useApi";
import { useChannel, type WsStatus } from "../../lib/ws";

type Tab = "tree" | "grid" | "stats";

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
  const [tab, setTabState] = useState<Tab>(params.get("tab") === "thong-ke" ? "stats" : "tree"); // link chia sẻ mở thẳng tab Thống kê
  const setTab = (t: Tab) => {
    setTabState(t);
    const p = new URLSearchParams(params);
    if (t === "stats") p.set("tab", "thong-ke");
    else p.delete("tab");
    setParams(p, { replace: true });
  };
  const alerts = s.alerts ?? [];
  const goNode = (nodeId?: string | null) => nodeId && navigate(`/gv/classes/${classId}/nodes/${nodeId}`);
  return (
    <>
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

      <div role="tablist" aria-label="Chế độ xem" className="inline-flex gap-1 rounded-lg bg-app p-1">
        {(
          [
            ["tree", "Chế độ cây"],
            ["grid", "Lưới SV × Nút"],
            ["stats", "Thống kê"],
          ] as const
        ).map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)} className={`rounded-md px-4 py-1.5 text-body-m font-semibold ${tab === id ? "bg-surface shadow-card" : "text-ink-500"}`}>
            {label}
          </button>
        ))}
      </div>

      <div className={`grid gap-4 ${tab === "stats" ? "" : "xl:grid-cols-[1fr_380px]"}`}>
        {tab === "stats" ? (
          <div className="min-w-0">
            <StatsTab s={s} classId={classId} hideNames={hideNames} />
          </div>
        ) : (
        <section aria-label={tab === "tree" ? "Cây kỹ năng theo tỉ lệ Đạt" : "Lưới sinh viên"} className="space-y-3 rounded-lg border border-line-soft bg-surface p-4">
          {tab === "tree" ? (
            s.tree ? (
              <SkillTree
                mode="heatmap"
                nodes={s.tree.nodes}
                edges={s.tree.edges}
                heat={heatByKey(s)}
                details={detailsByKey(s)}
                rootCauseKey={rootCauseKey(s)}
                height={440}
                onNodeClick={(n) => goNode(n.id)}
              />
            ) : (
              <p className="text-body-m text-ink-500">Lớp chưa có cây đang phát hành.</p>
            )
          ) : (
            <HeatGrid rows={s.grid} nodes={s.nodes} hideNames={hideNames} />
          )}
        </section>
        )}

        <aside aria-label="Cảnh báo điểm nghẽn" className="space-y-3">
          <h2 className="flex items-center gap-2 text-h3 font-semibold">
            <TriangleAlert aria-hidden size={18} className="text-red-700" /> Cảnh báo điểm nghẽn
          </h2>
          {alerts.length === 0 ? (
            <p className="rounded-lg border border-dashed border-line-strong p-4 text-body-m text-ink-500">Chưa có điểm nghẽn nào – lớp đang tiến triển ổn.</p>
          ) : (
            alerts.map((a) => (
              <div key={a.nodeId} className="space-y-2 rounded-lg border border-red-700/40 bg-st-fail/30 p-4">
                <p className="text-h3 font-bold text-red-900">{a.message}</p>
                {a.conditionalFailRate != null && (
                  <p className="text-body-s">
                    {Math.round(a.conditionalFailRate * 100)}% SV trượt nút này cũng chưa Đạt nút gốc
                    {a.failedCount != null && ` (${a.failedCount} SV)`}.
                  </p>
                )}
                <div className="flex gap-2">
                  <button onClick={() => goNode(a.rootCauseNodeId)} className="rounded-md border border-red-700/50 bg-surface px-3 py-1.5 text-body-s font-semibold text-red-900">
                    Xem chi tiết nút
                  </button>
                  <Link to={`/gv/classes/${classId}/matching`} className="rounded-md border border-line-strong bg-surface px-3 py-1.5 text-body-s font-semibold">
                    Ghép cặp ưu tiên
                  </Link>
                </div>
              </div>
            ))
          )}
        </aside>
      </div>
    </>
  );
}
