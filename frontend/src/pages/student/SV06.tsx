import { ArrowLeft, CircleCheck, CircleX, Network, Play, Sparkles, TriangleAlert } from "lucide-react";
import { useEffect } from "react";
import { Link, useParams } from "react-router";
import { AsyncView, LoadingBox } from "../../components/AsyncView";
import { ApiError, apiCall, type Schema } from "../../lib/api";
import { CRITERION_LABEL } from "../../lib/criteria";
import { useApi } from "../../lib/useApi";

type Result = Schema<"SessionResult">;
const FLAG_LABEL: Partial<Record<Schema<"FlagType">, string>> = {
  PASTE_SUSPECTED: "Phát hiện dán văn bản dài – giảng viên có thể xem lại phiên này.",
  LOW_STT_CONFIDENCE: "Bản chép lời có độ tin cậy thấp ở một số đoạn.",
};
const POLL_MS = 3000;

/** SV-06 Kết quả & phản hồi (Figma 25:1410, FR-TB-13, GD-08). Chưa chấm xong (409) thì tự hỏi lại. */
export default function StudentResult() {
  const { sessionId = "" } = useParams();
  const result = useApi((signal) => apiCall("get", "/sessions/{session_id}/result", { path: { session_id: sessionId }, signal }), [sessionId]);
  const notReady = result.status === "error" && result.error instanceof ApiError && result.error.code === "RESULT_NOT_READY";
  useEffect(() => {
    if (!notReady) return;
    const t = setTimeout(result.reload, POLL_MS);
    return () => clearTimeout(t);
  }, [notReady, result.reload]);

  if (notReady)
    return (
      <div className="space-y-3">
        <LoadingBox text="Whybi đang chấm lời giảng của bạn…" />
      </div>
    );
  return <AsyncView state={result}>{(r) => <ResultView r={r} />}</AsyncView>;
}

function ResultView({ r }: { r: Result }) {
  const passed = r.verdict === "PASSED";
  const next = r.unlockedNodes[0];
  const mapUrl = `/sv/classes/${r.classId}`;
  return (
    <div className="space-y-4">
      <header className="flex items-center gap-3">
        <Link to={mapUrl} aria-label="Quay lại bản đồ học tập" className="rounded-md border border-line-soft p-2">
          <ArrowLeft aria-hidden size={18} />
        </Link>
        <h1 className="text-h2 font-bold">Kết quả phiên</h1>
      </header>

      <section
        aria-label="Kết luận"
        className={`space-y-2 rounded-xl p-5 text-center ${passed ? "bg-st-pass text-green-900" : "bg-st-fail text-red-900"}`}
      >
        <p className="flex items-center justify-center gap-2 text-body-m font-bold tracking-widest">
          {passed ? <CircleCheck aria-hidden size={18} /> : <CircleX aria-hidden size={18} />}
          {passed ? "ĐẠT" : "CHƯA ĐẠT"}
        </p>
        <p className="text-display font-bold">{Math.round(r.totalScore)}/100</p>
        <p className="text-body-s">Ngưỡng Đạt {r.passThreshold}</p>
      </section>

      <section aria-label="Điểm theo tiêu chí" className="space-y-3 rounded-lg border border-line-soft bg-surface p-4">
        <h2 className="caps">Điểm theo tiêu chí</h2>
        {r.criteria.map((c) => {
          const pct = c.max > 0 ? (c.score / c.max) * 100 : 0;
          return (
            <div key={c.code} className="space-y-1">
              <div className="flex items-baseline justify-between">
                <span className="font-semibold">
                  {CRITERION_LABEL[c.code]} <span className="text-body-s font-normal text-ink-500">{Math.round(c.weight * 100)}%</span>
                </span>
                <span className="font-bold">
                  {Math.round(c.score)}/{Math.round(c.max)}
                </span>
              </div>
              <div role="progressbar" aria-label={CRITERION_LABEL[c.code]} aria-valuemin={0} aria-valuemax={c.max} aria-valuenow={c.score} className="h-2 overflow-hidden rounded-full bg-app">
                <div className={`h-full ${pct >= 70 ? "bg-teal" : "bg-honey"}`} style={{ width: `${pct}%` }} />
              </div>
              {c.rationale && <p className="text-body-s text-ink-500">{c.rationale}</p>}
            </div>
          );
        })}
      </section>

      {r.strengths.length > 0 && (
        <Card icon={<CircleCheck aria-hidden size={16} />} title="Điều bạn làm tốt" className="border-green-700/30 bg-st-pass/60 text-green-900" items={r.strengths} />
      )}
      {r.reviewHints.length > 0 && (
        <Card icon={<Sparkles aria-hidden size={16} />} title="Nên ôn thêm (không lộ đáp án)" className="border-teal/30 bg-teal-soft text-teal" items={r.reviewHints} />
      )}
      {r.sourcePages.length > 0 && <p className="text-body-s text-ink-500">Xem lại giáo trình: trang {r.sourcePages.join(", ")}.</p>}
      {r.flags.map((f) =>
        FLAG_LABEL[f] ? (
          <p key={f} role="note" className="flex items-start gap-2 text-body-s text-honey-deep">
            <TriangleAlert aria-hidden size={14} className="mt-0.5 shrink-0" /> {FLAG_LABEL[f]}
          </p>
        ) : null,
      )}

      <div className="grid grid-cols-2 gap-2">
        <Link to={mapUrl} className="inline-flex items-center justify-center gap-2 rounded-md border border-line-strong px-4 py-2 font-semibold">
          <Network aria-hidden size={16} /> Xem bản đồ
        </Link>
        <Link
          to={next ? `${mapUrl}/nodes/${next}` : mapUrl}
          className="inline-flex items-center justify-center gap-2 rounded-md bg-honey px-4 py-2 font-semibold text-ink-900"
        >
          <Play aria-hidden size={16} /> {next ? "Giảng nút tiếp theo" : passed ? "Chọn nút khác" : "Giảng lại"}
        </Link>
      </div>
    </div>
  );
}

function Card({ icon, title, items, className }: { icon: React.ReactNode; title: string; items: string[]; className: string }) {
  return (
    <section className={`space-y-1 rounded-lg border p-4 ${className}`}>
      <h2 className="flex items-center gap-2 font-semibold">
        {icon} {title}
      </h2>
      {items.map((t) => (
        <p key={t} className="text-body-m">
          {t}
        </p>
      ))}
    </section>
  );
}
