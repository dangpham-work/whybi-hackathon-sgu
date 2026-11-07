import { Check, ChevronDown, Info, X } from "lucide-react";
import { useState } from "react";
import { AsyncView } from "../../components/AsyncView";
import { TurnAudio } from "../../components/TurnAudio";
import { apiCall, type Schema } from "../../lib/api";
import { useApi } from "../../lib/useApi";

type Result = Schema<"SessionResult">;
type Filter = "ALL" | "PASSED" | "FAILED";
const vn = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "");

/** SV-08 Lịch sử phiên (Figma 25:1031, FR-TB-15, GD-14/16): kết quả các phiên đã chấm, mở ra xem hội thoại và nghe lại ghi âm. */
export default function StudentHistory() {
  const sessions = useApi((signal) => apiCall("get", "/me/sessions", { signal }), []);
  const [filter, setFilter] = useState<Filter>("ALL");
  return (
    <div className="space-y-4">
      <h1 className="text-h1 font-bold">Lịch sử phiên</h1>
      <AsyncView state={sessions} isEmpty={(l) => l.length === 0} empty="Bạn chưa có phiên nào được chấm. Hãy giảng một nút để bắt đầu.">
        {(list) => {
          const passed = list.filter((r) => r.verdict === "PASSED").length;
          const avg = Math.round(list.reduce((n, r) => n + r.totalScore, 0) / list.length);
          const shown = list.filter((r) => filter === "ALL" || r.verdict === filter);
          return (
            <>
              <dl className="grid grid-cols-3 gap-2 text-center">
                <Stat label="Phiên" value={list.length} />
                <Stat label="Đạt" value={passed} tone="text-green-800" />
                <Stat label="Điểm TB" value={avg} tone="text-teal" />
              </dl>
              <div role="group" aria-label="Lọc kết quả" className="flex gap-2">
                {(
                  [
                    ["ALL", "Tất cả"],
                    ["PASSED", "Đạt"],
                    ["FAILED", "Chưa đạt"],
                  ] as const
                ).map(([id, label]) => (
                  <button key={id} aria-pressed={filter === id} onClick={() => setFilter(id)} className={`rounded-full border px-4 py-1.5 text-body-m font-semibold ${filter === id ? "border-ink-900 bg-ink-900 text-white" : "border-line-strong bg-surface"}`}>
                    {label}
                  </button>
                ))}
              </div>
              <ul aria-label="Các phiên" className="divide-y divide-line-soft rounded-lg border border-line-soft bg-surface">
                {shown.map((r) => (
                  <Row key={r.sessionId} r={r} />
                ))}
                {shown.length === 0 && <li className="p-4 text-body-m text-ink-500">Không có phiên nào khớp bộ lọc.</li>}
              </ul>
              <p className="flex items-start gap-2 rounded-lg bg-app px-3 py-2 text-body-s text-ink-500">
                <Info aria-hidden size={14} className="mt-0.5 shrink-0" /> Ghi âm chỉ được lưu khi bạn đồng ý và sẽ tự xóa sau một thời gian (BR-13).
              </p>
            </>
          );
        }}
      </AsyncView>
    </div>
  );
}

function Stat({ label, value, tone = "" }: { label: string; value: number; tone?: string }) {
  return (
    <div className="rounded-lg border border-line-soft bg-surface p-3">
      <dd className={`text-h1 font-bold ${tone}`}>{value}</dd>
      <dt className="text-body-s text-ink-500">{label}</dt>
    </div>
  );
}

function Row({ r }: { r: Result }) {
  const [open, setOpen] = useState(false);
  const passed = r.verdict === "PASSED";
  return (
    <li>
      <button aria-expanded={open} onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-3 p-3 text-left">
        <span aria-hidden className={`flex size-9 shrink-0 items-center justify-center rounded-full ${passed ? "bg-st-pass text-green-900" : "bg-st-fail text-red-900"}`}>
          {passed ? <Check size={18} /> : <X size={18} />}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block font-semibold">
            {passed ? "Đạt" : "Chưa đạt"} · {Math.round(r.totalScore)}/100
          </span>
          <span className="block text-body-s text-ink-500">{vn(r.completedAt)}</span>
        </span>
        <ChevronDown aria-hidden size={16} className={open ? "rotate-180" : ""} />
      </button>
      {open && <Detail id={r.sessionId} />}
    </li>
  );
}

/** Chi tiết một phiên: tên nút, hội thoại và ghi âm (còn hạn lưu). Tải khi SV mở. */
function Detail({ id }: { id: string }) {
  const d = useApi((signal) => apiCall("get", "/me/sessions/{session_id}", { path: { session_id: id }, signal }), [id]);
  return (
    <div className="space-y-2 border-t border-line-soft bg-app p-3">
      <AsyncView state={d}>
        {(s) => (
          <>
            <p className="font-semibold">{s.nodeTitle ?? s.nodeKey}</p>
            <ol className="space-y-2">
              {s.turns.map((t) => (
                <li key={t.turnNo} className={`rounded-md px-3 py-2 text-body-m ${t.speaker === "STUDENT" ? "bg-teal-soft" : "bg-surface"}`}>
                  <span className="caps block">{t.speaker === "STUDENT" ? "Bạn" : "Whybi"}</span>
                  {t.content}
                  {t.audioUrl && <TurnAudio audioUrl={t.audioUrl} />}
                </li>
              ))}
            </ol>
          </>
        )}
      </AsyncView>
    </div>
  );
}
