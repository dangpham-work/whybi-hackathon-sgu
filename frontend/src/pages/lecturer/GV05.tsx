import { Mic, TriangleAlert, Users, Wifi } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { AsyncView } from "../../components/AsyncView";
import { HeatGrid } from "../../components/HeatGrid";
import { SkillTree } from "../../components/SkillTree";
import { apiCall } from "../../lib/api";
import { applyHeatmapEvent, detailsByKey, heatByKey, rootCauseKey, type Snapshot } from "../../lib/heatmap";
import { useApi } from "../../lib/useApi";
import { useChannel, type WsStatus } from "../../lib/ws";

type Tab = "tree" | "grid";

/** GV-05 Dashboard bản đồ nhiệt (Figma 17:1447, FR-HM-01…06, GD-10). Ảnh chụp + kênh `class:{id}:heatmap`, không cần tải lại trang. */
export default function LecturerHeatmap() {
  const { classId = "" } = useParams();
  const snap = useApi((signal) => apiCall("get", "/classes/{class_id}/heatmap", { path: { class_id: classId }, signal }), [classId]);
  const [live, setLive] = useState<Snapshot>();
  useEffect(() => setLive(snap.data), [snap.data]);

  const status = useChannel(`class:${classId}:heatmap`, (e) => {
    if (e.event === "reconnected") snap.reload(); // mất kết nối thì dữ liệu có thể đã lỡ – lấy lại ảnh chụp (UC10 E1)
    else setLive((s) => (s ? applyHeatmapEvent(s, e) : s));
  });

  return (
    <div className="space-y-5 p-4 lg:p-7">
      <h1 className="text-h1 font-bold">Bản đồ nhiệt lớp học</h1>
      <AsyncView state={snap.status === "success" && live ? { ...snap, data: live } : snap} loadingText="Đang tải bản đồ nhiệt…">
        {(s) => <Dashboard s={s} classId={classId} wsStatus={status} />}
      </AsyncView>
    </div>
  );
}

const WS_TEXT: Partial<Record<WsStatus, string>> = { reconnecting: "Mất kết nối – đang nối lại…", connecting: "Đang kết nối…", closed: "Mất kết nối" };

function Dashboard({ s, classId, wsStatus }: { s: Snapshot; classId: string; wsStatus: WsStatus }) {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("tree");
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
          ] as const
        ).map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)} className={`rounded-md px-4 py-1.5 text-body-m font-semibold ${tab === id ? "bg-surface shadow-card" : "text-ink-500"}`}>
            {label}
          </button>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
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
            <HeatGrid rows={s.grid} nodes={s.nodes} />
          )}
        </section>

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
