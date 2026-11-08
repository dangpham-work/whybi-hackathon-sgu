import { ChevronLeft, CircleCheck, CircleSlash, Clock, Ellipsis, Play, PlayCircle, RotateCcw, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import { AsyncView, EmptyBox, ErrorBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { BLOOM_LABEL } from "../../components/SkillTree";
import { StartSessionError, useStartSession } from "../../components/StartSession";
import { StatusBadge } from "../../components/StatusBadge";
import { apiCall, errorText } from "../../lib/api";
import { clock, learnerView, prerequisitesOf, waitingRetry, type LearnerItem, type LearnerView } from "../../lib/learner";
import { MASTERY } from "../../lib/status";
import { useApi } from "../../lib/useApi";

/**
 * SV-03 Chi tiết nút (Figma 25:826, FR-TB-02, GD-06): trạng thái, điểm cao nhất, số lượt, tiên quyết còn thiếu,
 * giờ được thử lại (BR-11) và nút "Bắt đầu giảng cho AI".
 * Dữ liệu: GET /classes/{classId}/my-map (C2-10) – tra nút theo `nodeId` của NodeProgress.
 * Chưa có trong hợp đồng nên chưa hiện: khối "Gợi ý ôn tập" của Figma (cần dữ liệu phản hồi lượt trước).
 */
export default function NodeDetail() {
  const { classId = "", nodeId = "" } = useParams();
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
  const view = useMemo(() => (map.data ? learnerView(map.data) : null), [map.data]);
  const item = view?.items.find((i) => i.progress.nodeId === nodeId);
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Link
          to={`/sv/classes/${classId}`}
          aria-label="Quay lại bản đồ học tập"
          className="flex size-8 shrink-0 items-center justify-center rounded-md bg-surface text-ink-700 shadow-card hover:bg-app"
        >
          <ChevronLeft aria-hidden size={18} />
        </Link>
        <div className="min-w-0">
          <h1 className="truncate text-h1 font-bold">{item ? `${item.node.code ? `${item.node.code} — ` : ""}${item.node.title}` : "Chi tiết nút"}</h1>
          {item && (
            <p className="text-body-s text-ink-500">
              {[item.node.chapterRef, `Bloom: ${BLOOM_LABEL[item.node.bloomLevel]}`].filter(Boolean).join(" · ")}
            </p>
          )}
        </div>
      </div>
      <AsyncView state={map} loadingText="Đang tải chi tiết nút…">
        {() =>
          item && view ? (
            <Detail key={item.progress.nodeId} item={item} view={view} onAbandoned={map.reload} />
          ) : (
            <EmptyBox>Không tìm thấy nút này trong bản đồ học tập của bạn (cây có thể vừa được cập nhật).</EmptyBox>
          )
        }
      </AsyncView>
    </div>
  );
}

function Detail({ item, view, onAbandoned }: { item: LearnerItem; view: LearnerView; onAbandoned: () => void }) {
  const p = item.progress;
  const look = MASTERY[p.state];
  const Icon = look.icon;
  const best = p.bestScore != null ? Math.round(p.bestScore) : null;
  const prereqs = prerequisitesOf(item.node.key, view);
  const { start, busy, failure } = useStartSession();
  const rubric = item.node.rubric;
  const steps: [string, string][] = [
    ["Bạn giảng khái niệm cho Whybi", "Bằng giọng nói hoặc gõ văn bản, 3–8 phút"],
    [rubric ? `Whybi hỏi vặn ít nhất ${rubric.minChallenges} câu` : "Whybi hỏi vặn theo rubric", "Về ý còn thiếu, quan niệm sai và tình huống biên"],
    ["Nhận kết quả theo 5 tiêu chí", rubric
      ? `Đạt khi ≥ ${rubric.passThreshold} điểm và vượt ≥ ${rubric.minPassedChallenges} câu phản biện, nêu đủ ý bắt buộc và sửa các quan niệm sai nghiêm trọng.`
      : "Điều kiện Đạt theo rubric do giảng viên phê duyệt."],
  ];

  return (
    <>
      <section aria-label="Trạng thái nút" className={`space-y-3 rounded-lg border p-4 ${look.className}`}>
        <div className="flex items-center justify-between">
          <p className="flex items-center gap-2 text-h3 font-bold">
            <Icon aria-hidden size={18} strokeWidth={2.5} />
            {look.label}
          </p>
          {p.attempts > 0 && <span className="rounded-full bg-surface px-2 py-1 text-body-s font-semibold text-ink-700">Lượt {p.attempts}</span>}
        </div>
        <dl className="grid grid-cols-3 gap-2">
          <Stat value={best != null ? String(best) : "—"} label="điểm cao nhất" align="start" />
          <Stat value={rubric ? String(rubric.passThreshold) : "—"} label="ngưỡng Đạt" align="center" />
          <Stat value={rubric ? `≥ ${rubric.minChallenges}` : "—"} label="câu phản biện" align="end" />
        </dl>
        <div
          role="progressbar"
          aria-label="Điểm cao nhất so với 100"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={best ?? 0}
          className="h-2 overflow-hidden rounded-full bg-surface/70"
        >
          <div className="h-full rounded-full bg-current" style={{ width: `${best ?? 0}%` }} />
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-line-soft bg-surface p-4 shadow-card">
        <Eligibility item={item} view={view} onAbandoned={onAbandoned} />
        <h2 id="sv03-prereq" className="caps">
          Nút tiên quyết
        </h2>
        {prereqs.length === 0 ? (
          <p className="text-body-m text-ink-500">Nút này không có tiên quyết.</p>
        ) : (
          <ul aria-labelledby="sv03-prereq" className="space-y-2">
            {prereqs.map((pre) => (
              <li key={pre.node.key} className="flex items-center gap-2 text-body-m">
                {pre.node.code && <span className="w-8 shrink-0 text-body-s font-bold text-ink-500">{pre.node.code}</span>}
                <span className="min-w-0 flex-1 truncate text-ink-700">{pre.node.title}</span>
                <StatusBadge kind="mastery" value={pre.progress.state} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-3 rounded-lg border border-line-soft bg-surface p-4 shadow-card">
        <h2 className="caps">Phiên giảng sẽ diễn ra thế nào</h2>
        <ol className="space-y-3">
          {steps.map(([title, sub], i) => (
            <li key={title} className="flex items-center gap-3">
              <span aria-hidden className="flex size-6 shrink-0 items-center justify-center rounded-full bg-teal-soft text-body-s font-bold text-teal">
                {i + 1}
              </span>
              <div>
                <p className="text-body-m font-semibold">{title}</p>
                <p className="text-body-s text-ink-500">{sub}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <div className="sticky bottom-20 space-y-2 rounded-lg border border-line-soft bg-surface p-3 shadow-card">
        <StartSessionError failure={failure} />
        <Button className="w-full py-2.5" disabled={!p.canStart || busy} onClick={() => start(p.nodeId)}>
          <Play aria-hidden size={16} /> Bắt đầu giảng cho AI
        </Button>
      </div>
    </>
  );
}

function Stat({ value, label, align }: { value: string; label: string; align: "start" | "center" | "end" }) {
  const cls = align === "start" ? "items-start" : align === "center" ? "items-center" : "items-end";
  return (
    <div className={`flex flex-col-reverse ${cls}`}>
      <dt className="text-body-s">{label}</dt>
      <dd className="text-h1 font-bold">{value}</dd>
    </div>
  );
}

/** Dòng "có bắt đầu được không" – chữ trung tính + biểu tượng (màu trạng thái đã ở thẻ trên, lấy từ MASTERY); lý do lấy từ NodeProgress. */
function Eligibility({ item, view, onAbandoned }: { item: LearnerItem; view: LearnerView; onAbandoned: () => void }) {
  const p = item.progress;
  const row = (icon: ReactNode, text: string, cls: string) => (
    <p className={`flex items-center gap-2 text-body-m font-bold ${cls}`}>
      {icon}
      {text}
    </p>
  );
  if (p.canStart) return row(<CircleCheck aria-hidden size={16} />, "Đủ điều kiện bắt đầu", "text-ink-900");
  if (p.state === "IN_PROGRESS")
    return (
      <div className="space-y-2">
        {row(<Ellipsis aria-hidden size={16} />, "Bạn đang có phiên giảng ở nút này", "text-ink-900")}
        {p.lastSessionId && (
          <div className="flex flex-wrap items-center gap-3">
            <Link to={`/sv/sessions/${p.lastSessionId}`} className="inline-flex items-center gap-1 text-body-m font-semibold text-teal hover:underline">
              <PlayCircle aria-hidden size={16} /> Tiếp tục phiên đang giảng
            </Link>
            <AbandonSession sessionId={p.lastSessionId} onAbandoned={onAbandoned} />
          </div>
        )}
      </div>
    );
  if (p.state === "MASTERED") {
    const Done = MASTERY.MASTERED.icon;
    return row(<Done aria-hidden size={16} />, "Bạn đã Đạt nút này", "text-ink-900");
  }
  if (waitingRetry(p)) return row(<Clock aria-hidden size={16} />, `Thử lại lúc ${clock(p.retryAt!)} (nghỉ 10 phút sau lần Chưa đạt)`, "text-ink-900");
  if (p.missingPrerequisites.length) {
    const names = p.missingPrerequisites.map((k) => {
      const n = view.byKey.get(k)?.node;
      return n ? `${n.code ? `${n.code} ` : ""}${n.title}` : k;
    });
    return row(<CircleSlash aria-hidden size={16} />, `Còn thiếu tiên quyết: ${names.join(", ")}`, "text-ink-700");
  }
  return row(<CircleSlash aria-hidden size={16} />, `Chưa bắt đầu được nút này (${MASTERY[p.state].label})`, "text-ink-700");
}

/** Bug #189: phiên hỏng giữa chừng (lỗi LLM ở lượt sau câu mở đầu) kẹt mãi IN_PROGRESS – SV tự bỏ để mở lại. */
function AbandonSession({ sessionId, onAbandoned }: { sessionId: string; onAbandoned: () => void }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>();

  async function confirm() {
    setBusy(true);
    setFailure(undefined);
    try {
      await apiCall("post", "/sessions/{session_id}/abandon", { path: { session_id: sessionId } });
      setAsking(false);
      onAbandoned();
    } catch (err) {
      setFailure(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setAsking(true)}
        className="inline-flex items-center gap-1 text-body-m font-semibold text-ink-500 hover:text-ink-700 hover:underline"
      >
        <RotateCcw aria-hidden size={16} /> Bỏ phiên này, bắt đầu lại
      </button>
      {asking && (
        <AbandonConfirmDialog
          busy={busy}
          failure={failure}
          onCancel={() => setAsking(false)}
          onConfirm={confirm}
        />
      )}
    </>
  );
}

function AbandonConfirmDialog({
  busy,
  failure,
  onCancel,
  onConfirm,
}: {
  busy: boolean;
  failure: unknown;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.querySelectorAll<HTMLButtonElement>("button")?.[0]?.focus();
  }, []);
  function trap(e: ReactKeyboardEvent) {
    if (e.key === "Escape") return onCancel();
    if (e.key !== "Tab") return;
    const buttons = Array.from(ref.current?.querySelectorAll<HTMLButtonElement>("button") ?? []);
    const i = buttons.indexOf(document.activeElement as HTMLButtonElement);
    e.preventDefault();
    buttons[(i + (e.shiftKey ? buttons.length - 1 : 1)) % buttons.length]?.focus();
  }
  return (
    <div className="fixed inset-0 z-20 flex items-end justify-center bg-ink-900/40 p-4 sm:items-center">
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby="abandon-title"
        aria-describedby="abandon-desc"
        onKeyDown={trap}
        className="w-full max-w-sm space-y-3 rounded-xl bg-surface p-5 shadow-dialog"
      >
        <h2 id="abandon-title" className="flex items-center gap-2 text-h3 font-semibold">
          <TriangleAlert aria-hidden size={20} className="text-honey-deep" /> Bỏ phiên đang dở?
        </h2>
        <p id="abandon-desc" className="text-body-m text-ink-700">
          Phiên đang dở sẽ bị hủy, không được chấm. Dùng khi phiên cũ bị lỗi và không tiếp tục được nữa.
        </p>
        {failure !== undefined && <ErrorBox text={errorText(failure)} />}
        <div className="flex flex-col gap-2 sm:flex-row-reverse">
          <Button onClick={onConfirm} disabled={busy} className="justify-center">
            Bỏ phiên, bắt đầu lại
          </Button>
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-md px-4 py-2 text-body-m font-semibold text-ink-700 hover:bg-app"
          >
            Hủy
          </button>
        </div>
      </div>
    </div>
  );
}
