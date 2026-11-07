import { ChevronRight, Info, List, Network, Play, PlayCircle, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { AsyncView } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { SkillTree } from "../../components/SkillTree";
import { StartSessionError, useStartSession } from "../../components/StartSession";
import { StatusLegend } from "../../components/StatusBadge";
import { apiCall } from "../../lib/api";
import { learnerView, nextToLearn, nodeDetail, nodeName, type LearnerItem, type LearnerView, type MyMap } from "../../lib/learner";
import { MASTERY } from "../../lib/status";
import { useApi } from "../../lib/useApi";

/**
 * SV-02 Bản đồ học tập (Figma 25:714, FR-TB-01, GD-06): tiến độ, cây kỹ năng tô theo trạng thái, nút "Bắt đầu giảng"
 * cho nút nên học tiếp – từ đăng nhập tới bắt đầu phiên ≤ 3 thao tác (NFR-11).
 * Dữ liệu: GET /classes/{classId}/my-map → MyMap (hợp đồng C2-10, còn 501 tới khi C2-10 xong).
 * Chưa có trong hợp đồng nên chưa hiện: chuỗi ngày học liên tiếp, nhãn "GỐC LỚP" của bản đồ nhiệt, tên lớp trên header.
 */
export default function LearningMap() {
  const { classId = "" } = useParams();
  const map = useApi((signal) => apiCall("get", "/classes/{class_id}/my-map", { path: { class_id: classId }, signal }), [classId]);
  useEffect(() => {
    const now = Date.now();
    const retries = map.data?.progress.map((p) => p.retryAt ? Date.parse(p.retryAt) : 0).filter((at) => at > now) ?? [];
    if (!retries.length) return;
    // Hỏi lại MasteryService khi hết BR-11; không tự suy canStart ở trình duyệt.
    // setTimeout tràn khi trễ > 2^31-1 ms (~24,8 ngày) và chạy ngay → giới hạn để không reload liên tục.
    const timer = setTimeout(map.reload, Math.min(Math.min(...retries) - now, 2 ** 31 - 1));
    return () => clearTimeout(timer);
  }, [map.data, map.reload]);
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-h1 font-bold">Bản đồ học tập</h1>
        <p className="text-body-m text-ink-500">Giảng lại từng khái niệm cho Whybi để mở khóa nút tiếp theo.</p>
      </div>
      <AsyncView state={map} loadingText="Đang tải bản đồ học tập…" isEmpty={(m) => m.tree.nodes.length === 0} empty="Chưa có nút kỹ năng trong bản đồ học tập.">
        {(m) => <MapBody key={classId} map={m} classId={classId} />}
      </AsyncView>
    </div>
  );
}

function MapBody({ map, classId }: { map: MyMap; classId: string }) {
  const view = useMemo(() => learnerView(map), [map]);
  const [mode, setMode] = useState<"list" | "graph">("list");
  const next = nextToLearn(view);
  const running = view.items.find((i) => i.progress.state === "IN_PROGRESS" && i.progress.lastSessionId);
  return (
    <>
      <Progress mastered={map.masteredCount} total={map.totalCount} />
      {next ? <NextUp key={next.progress.nodeId} item={next} /> : running && <Resume item={running} />}

      <section aria-labelledby="sv02-tree" className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h2 id="sv02-tree" className="caps">
            Cây kỹ năng của bạn
          </h2>
          <div className="flex rounded-md border border-line-strong bg-surface p-0.5" role="group" aria-label="Kiểu hiển thị">
            <ModeButton active={mode === "list"} onClick={() => setMode("list")} icon={<List aria-hidden size={14} />} label="Danh sách" />
            <ModeButton active={mode === "graph"} onClick={() => setMode("graph")} icon={<Network aria-hidden size={14} />} label="Sơ đồ" />
          </div>
        </div>
        <p className="flex items-center gap-1 text-body-s text-ink-500">
          <Info aria-hidden size={12} /> Nhấn vào nút để xem chi tiết
        </p>
        {mode === "list" ? <NodeList view={view} classId={classId} /> : <NodeGraph view={view} classId={classId} />}
      </section>
      {mode === "list" && <StatusLegend kind="mastery" />}
    </>
  );
}

function ModeButton({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: ReactNode; label: string }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`inline-flex items-center gap-1 rounded px-2 py-1 text-body-s font-semibold ${active ? "bg-teal-soft text-teal" : "text-ink-500 hover:text-ink-900"}`}
    >
      {icon}
      {label}
    </button>
  );
}

function Progress({ mastered, total }: { mastered: number; total: number }) {
  const pct = total > 0 ? Math.round((mastered / total) * 100) : 0;
  const left = Math.max(total - mastered, 0);
  return (
    <section className="space-y-1.5 rounded-lg border border-line-soft bg-surface p-4 shadow-card">
      <div className="flex items-center justify-between text-body-m">
        <p id="sv02-progress" className="font-semibold">
          Tiến độ của bạn
        </p>
        <p className="font-bold text-teal">
          {mastered}/{total} nút
        </p>
      </div>
      <div
        role="progressbar"
        aria-labelledby="sv02-progress"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={mastered}
        className="h-2 overflow-hidden rounded-full bg-app"
      >
        <div className="h-full rounded-full bg-teal" style={{ width: `${pct}%` }} />
      </div>
      <p className="text-body-s text-ink-500">{left > 0 ? `Còn ${left} nút để hoàn thành môn học` : "Bạn đã Đạt mọi nút của môn học"}</p>
    </section>
  );
}

/** Lối tắt NFR-11: bắt đầu phiên ngay từ bản đồ, không cần mở SV-03. */
function NextUp({ item }: { item: LearnerItem }) {
  const { start, busy, failure } = useStartSession();
  const name = nodeName(item.node);
  return (
    <section aria-label="Học tiếp" className="space-y-3 rounded-lg border border-honey/50 bg-honey-soft p-4">
      <p className="flex items-center gap-2 text-body-s font-semibold text-honey-deep">
        <Sparkles aria-hidden size={14} /> Nên học tiếp
      </p>
      <p className="text-h3 font-semibold">{name}</p>
      <StartSessionError failure={failure} />
      <Button className="w-full py-2.5" disabled={busy} onClick={() => start(item.progress.nodeId)} aria-label={`Bắt đầu giảng ${name}`}>
        <Play aria-hidden size={16} /> Bắt đầu giảng
      </Button>
    </section>
  );
}

function Resume({ item }: { item: LearnerItem }) {
  return (
    <Link
      to={`/sv/sessions/${item.progress.lastSessionId}`}
      className="flex items-center gap-2 rounded-lg border border-honey/50 bg-honey-soft p-4 text-body-m font-semibold text-honey-deep"
    >
      <PlayCircle aria-hidden size={18} /> Tiếp tục phiên đang giảng: {nodeName(item.node)}
    </Link>
  );
}

const nodeHref = (classId: string, item: LearnerItem) => `/sv/classes/${classId}/nodes/${item.progress.nodeId}`;

function NodeList({ view, classId }: { view: LearnerView; classId: string }) {
  return (
    <ul aria-label="Cây kỹ năng của bạn" className="flex flex-col">
      {view.items.map((item, i) => {
        const look = MASTERY[item.progress.state];
        const Icon = look.icon;
        const detail = nodeDetail(item.progress, view.byKey);
        return (
          <li key={item.node.key} className="flex flex-col items-center">
            {i > 0 && <span aria-hidden className="h-2.5 w-0.5 bg-line-strong" />}
            <Link
              to={nodeHref(classId, item)}
              aria-label={`${nodeName(item.node)} – ${detail}${item.frontier ? " · Nên học tiếp" : ""}`}
              className={`flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 focus-visible:outline-2 focus-visible:outline-teal ${look.className} ${
                item.frontier ? "border-2" : ""
              }`}
            >
              <span aria-hidden className="flex size-7 shrink-0 items-center justify-center rounded-full bg-surface/60">
                <Icon size={15} strokeWidth={2.5} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5">
                  {item.node.code && <span className="text-body-s font-bold">{item.node.code}</span>}
                  <span className="truncate text-body-m font-semibold">{item.node.title}</span>
                </span>
                <span className="block truncate text-body-s">{detail}</span>
              </span>
              {item.frontier && (
                <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-ink-900 px-2 py-0.5 text-caps font-bold text-honey">
                  <Sparkles aria-hidden size={10} /> Nên học tiếp
                </span>
              )}
              <ChevronRight aria-hidden size={15} className="shrink-0" />
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function NodeGraph({ view, classId }: { view: LearnerView; classId: string }) {
  const navigate = useNavigate();
  const mastery = Object.fromEntries(view.items.map((i) => [i.node.key, i.progress.state]));
  // SkillTree tự ghi chữ trạng thái ở đầu dòng phụ → bỏ chữ trạng thái lặp lại trong nodeDetail
  const details = Object.fromEntries(
    view.items.map((i) => {
      const label = MASTERY[i.progress.state].label;
      const text = nodeDetail(i.progress, view.byKey);
      return [i.node.key, text.startsWith(label) ? text.slice(label.length).replace(/^ · /, "").trim() : text];
    }),
  );
  return (
    <SkillTree
      mode="learner"
      nodes={view.map.tree.nodes}
      edges={view.map.tree.edges}
      mastery={mastery}
      details={details}
      height={520}
      onNodeClick={(n) => {
        const item = view.byKey.get(n.key);
        if (item) navigate(nodeHref(classId, item));
      }}
    />
  );
}
