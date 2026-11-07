import { Check, CircleX, TriangleAlert } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router";
import { AsyncView, EmptyBox } from "../../components/AsyncView";
import { TurnAudio } from "../../components/TurnAudio";
import { apiCall, type Schema } from "../../lib/api";
import { CRITERION_LABEL, FLAG_LABEL } from "../../lib/criteria";
import { useApi } from "../../lib/useApi";

type Session = Schema<"ProfileSession">;

/**
 * GV-08 Transcript & ghi âm (Figma 19:2212, FR-HM-07, FR-TB-14, GD-13).
 * API chỉ trả transcript trong hồ sơ SV (`/classes/{id}/students/{id}/profile`) nên đường dẫn mang theo `?classId=&studentId=` (GV-07 tạo sẵn).
 */
export default function LecturerSession() {
  const { sessionId = "" } = useParams();
  const [q] = useSearchParams();
  const classId = q.get("classId");
  const studentId = q.get("studentId");
  const profile = useApi(
    (signal) =>
      classId && studentId
        ? apiCall("get", "/classes/{class_id}/students/{student_id}/profile", { path: { class_id: classId, student_id: studentId }, signal })
        : Promise.resolve(null),
    [classId, studentId],
  );
  return (
    <div className="space-y-5 p-4 lg:p-7">
      <AsyncView state={profile} loadingText="Đang tải transcript…">
        {(p) => {
          const s = p?.sessions.find((x) => x.sessionId === sessionId);
          if (!p || !s) return <EmptyBox>Không tìm thấy phiên này. Hãy mở từ hồ sơ sinh viên (GV-07).</EmptyBox>;
          return <View s={s} studentName={p.fullName} studentCode={p.studentCode} backTo={`/gv/classes/${p.classId}/students/${p.studentId}`} />;
        }}
      </AsyncView>
    </div>
  );
}

function View({ s, studentName, studentCode, backTo }: { s: Session; studentName: string; studentCode: string; backTo: string }) {
  const r = s.result;
  const passed = r?.verdict === "PASSED";
  const questions = s.turns.filter((t) => t.turnType === "QUESTION").length;
  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-h1 font-bold">Phiên giảng lại · {s.nodeTitle ?? s.nodeKey}</h1>
          <p className="text-body-m text-ink-500">
            {studentName} · {studentCode} · lượt {s.attemptNo}
          </p>
          <Link to={backTo} className="text-body-m font-semibold text-teal hover:underline">
            ← Hồ sơ sinh viên
          </Link>
        </div>
        {r && (
          <span className={`inline-flex items-center gap-1 rounded-full px-4 py-2 font-semibold ${passed ? "bg-st-pass text-green-900" : "bg-st-fail text-red-900"}`}>
            {passed ? <Check aria-hidden size={16} /> : <CircleX aria-hidden size={16} />} {passed ? "Đạt" : "Chưa đạt"} · {Math.round(r.totalScore)}/100
          </span>
        )}
      </header>

      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        <section aria-label="Bản chép lời" className="space-y-3 rounded-lg border border-line-soft bg-surface p-4">
          <h2 className="flex items-center justify-between text-h3 font-semibold">
            Bản chép lời <span className="rounded-full bg-app px-2 py-0.5 text-body-s font-normal">{questions} lượt hỏi đáp</span>
          </h2>
          {s.turns.length === 0 && <p className="text-body-m text-ink-500">Phiên chưa có lượt nào.</p>}
          <ol className="space-y-3">
            {s.turns.map((t) => {
              const mine = t.speaker === "STUDENT";
              return (
                <li key={t.turnNo} className={`flex ${mine ? "justify-end" : ""}`}>
                  <div className={`max-w-[85%] space-y-1 rounded-lg px-3 py-2 ${mine ? "bg-teal-soft" : "bg-app"}`}>
                    <p className="caps">
                      {mine ? `Sinh viên · ${t.inputMode === "VOICE" ? "giọng nói" : "văn bản"}` : "Học trò tò mò (AI)"}
                    </p>
                    <p className="whitespace-pre-wrap text-body-m">{t.content}</p>
                    {t.audioUrl && <TurnAudio audioUrl={t.audioUrl} />}
                  </div>
                </li>
              );
            })}
          </ol>
        </section>

        <div className="space-y-4">
          {r && (
            <section aria-label="Điểm theo tiêu chí" className="space-y-3 rounded-lg border border-line-soft bg-surface p-4">
              <h2 className="flex justify-between text-h3 font-semibold">
                Điểm theo tiêu chí <span>{Math.round(r.totalScore)}/100</span>
              </h2>
              {r.criteria.map((c) => (
                <div key={c.code} className="space-y-1">
                  <div className="flex justify-between text-body-m font-semibold">
                    <span>
                      {CRITERION_LABEL[c.code]} <span className="font-normal text-ink-500">{Math.round(c.weight * 100)}%</span>
                    </span>
                    <span>
                      {Math.round(c.score)}/{Math.round(c.max)}
                    </span>
                  </div>
                  <div role="progressbar" aria-label={CRITERION_LABEL[c.code]} aria-valuemin={0} aria-valuemax={c.max} aria-valuenow={c.score} className="h-1.5 overflow-hidden rounded-full bg-app">
                    <div className={`h-full ${c.max && c.score / c.max >= 0.7 ? "bg-teal" : "bg-honey"}`} style={{ width: `${c.max ? (c.score / c.max) * 100 : 0}%` }} />
                  </div>
                  {c.rationale && <p className="text-body-s text-ink-500">{c.rationale}</p>}
                </div>
              ))}
            </section>
          )}
          <section aria-label="Cờ vi phạm và liêm chính" className="space-y-2 rounded-lg border border-line-soft bg-surface p-4">
            <h2 className="flex justify-between text-h3 font-semibold">
              Cờ vi phạm & liêm chính <span className="rounded-full bg-honey-soft px-2 py-0.5 text-body-s font-normal text-honey-deep">{r?.flags.length ?? 0} cảnh báo</span>
            </h2>
            {(r?.flags.length ?? 0) === 0 ? (
              <p className="flex items-center gap-2 rounded-md bg-st-pass px-3 py-2 text-body-m text-green-900">
                <Check aria-hidden size={16} /> Không phát hiện dấu hiệu bất thường.
              </p>
            ) : (
              r!.flags.map((f) => (
                <p key={f} className="flex items-start gap-2 rounded-md bg-honey-soft px-3 py-2 text-body-m text-honey-deep">
                  <TriangleAlert aria-hidden size={16} className="mt-0.5 shrink-0" /> {FLAG_LABEL[f] ?? f}
                </p>
              ))
            )}
          </section>
        </div>
      </div>
    </>
  );
}
