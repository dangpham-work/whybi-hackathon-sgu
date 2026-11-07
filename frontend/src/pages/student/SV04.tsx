import { CircleCheck, Info, Keyboard, LoaderCircle, Mic, Send, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ClipboardEvent, type FormEvent, type KeyboardEvent } from "react";
import { Link, useLocation, useParams } from "react-router";
import { DevelopingBox, ErrorBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { Logo } from "../../components/Logo";
import { Recorder } from "../../components/Recorder";
import { TranscriptConfirm } from "../../components/TranscriptConfirm";
import { ApiError, apiCall, errorText, type Schema } from "../../lib/api";
import { createTypingMeter } from "../../lib/typing-meter";
import { useChannel } from "../../lib/ws";

type Question = Schema<"Question">;
type InputMode = Schema<"InputMode">;
type SessionStatus = Schema<"SessionStatus">;
type Turn = Schema<"Turn">;

/**
 * Dữ liệu SV-03 truyền sang khi bấm "Bắt đầu giảng" (GD-06):
 *   navigate(`/sv/sessions/${created.sessionId}`, { state: { opening: created.opening, nodeTitle, inputMode } })
 * Chưa có GET /sessions/{id} nên tải lại trang sẽ mất câu mở đầu – màn chờ câu hỏi qua kênh session:{id}.
 */
export interface SessionLocationState {
  opening?: Question;
  nodeTitle?: string;
  inputMode?: InputMode;
  status?: SessionStatus;
}

type Message = { id: number; from: "tutee"; text: string } | { id: number; from: "student"; text: string; mode: InputMode } | { id: number; from: "notice"; text: string };

const MAX_TEXT = 20_000; // Turn.text 1–20 000 ký tự (hợp đồng C1-01)
const LIVE: SessionStatus[] = ["CREATED", "EXPLAINING", "CHALLENGING"];
const OPENING_WAIT_MS = 6_000; // chờ câu mở đầu qua WebSocket tối đa chừng này rồi cho SV giảng tiếp

/** Vị trí tin cuối cùng của một bên (lib ES2022 chưa có findLastIndex). */
function lastIndexOf(list: Message[], from: Message["from"]) {
  for (let i = list.length - 1; i >= 0; i--) if (list[i].from === from) return i;
  return -1;
}

const canRecord = () => typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

/** SV-04 Phiên giảng lại (Figma 25:1214, FR-TB-03…05, 08, GD-07): hội thoại với Whybi, giảng bằng giọng nói hoặc gõ chữ. */
export default function TeachingSession() {
  const { sessionId = "" } = useParams();
  const initial = (useLocation().state ?? {}) as SessionLocationState;

  const nextId = useRef(0);
  const [messages, setMessages] = useState<Message[]>(() =>
    initial.opening ? [{ id: nextId.current++, from: "tutee", text: initial.opening.text }] : [],
  );
  const [status, setStatus] = useState<SessionStatus>(initial.status ?? "EXPLAINING");
  const [progress, setProgress] = useState<{ asked: number; total: number }>({ asked: 0, total: 0 });
  const [pending, setPending] = useState<{ transcript: Schema<"Transcript">; audioUrl: string }>();
  const [mode, setMode] = useState<InputMode>(initial.inputMode ?? (canRecord() ? "VOICE" : "TEXT"));
  const [consented, setConsented] = useState(false);
  // Recorder gửi bản ghi từ callback onstop dựng trước lúc đồng ý ⇒ đọc consent qua ref, không qua closure cũ.
  const consentRef = useRef(false);
  const onConsent = useCallback((agreed: boolean) => {
    consentRef.current = agreed;
    setConsented(agreed);
  }, []);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>();
  const askedAt = useRef(Date.now());

  const turnType: Turn["turnType"] = status === "CHALLENGING" ? "ANSWER" : "EXPLANATION";
  const live = LIVE.includes(status);
  const noQuestion = live && !messages.some((m) => m.from === "tutee");
  // Tải lại trang thì mất câu mở đầu (chưa có GET /sessions/{id}); chờ kênh session:{id} một lúc rồi mở khóa ô trả lời.
  const [gaveUp, setGaveUp] = useState(false);
  useEffect(() => {
    if (!noQuestion) return;
    const t = setTimeout(() => setGaveUp(true), OPENING_WAIT_MS);
    return () => clearTimeout(t);
  }, [noQuestion]);
  const waiting = noQuestion && !gaveUp;

  /** Thêm câu hỏi của Whybi, bỏ trùng (cùng câu có thể tới từ TurnReply và từ WebSocket). */
  const addQuestion = useCallback((q: Question) => {
    setMessages((list) => {
      const lastTutee = lastIndexOf(list, "tutee");
      // câu này đã hiện và SV chưa trả lời → bỏ qua bản trùng
      if (lastTutee >= 0 && lastTutee > lastIndexOf(list, "student") && list[lastTutee].text === q.text) return list;
      return [...list, { id: nextId.current++, from: "tutee", text: q.text }];
    });
    askedAt.current = Date.now();
  }, []);

  useChannel(sessionId ? `session:${sessionId}` : null, (e) => {
    if (e.event === "session.question" && e.payload && typeof (e.payload as Question).text === "string") addQuestion(e.payload as Question);
  });

  /** Gửi một lượt; ném lỗi lại để ô gõ / Recorder giữ nội dung cho lần gửi lại. */
  async function postTurn(turn: Omit<Turn, "turnType" | "responseTimeMs">) {
    setBusy(true);
    setFailure(undefined);
    const responseTimeMs = Math.max(0, Date.now() - askedAt.current);
    // Hiện lời của SV ngay (trước khi máy chủ trả lời): câu hỏi tới sớm qua WebSocket vẫn nằm sau lời giảng, không bị trùng.
    const mine = nextId.current++;
    setMessages((list) => [...list, { id: mine, from: "student", text: turn.text, mode: turn.inputMode }]);
    try {
      const reply = await apiCall("post", "/sessions/{session_id}/turns", {
        path: { session_id: sessionId },
        body: { ...turn, turnType, responseTimeMs },
      });
      if (reply.notice) setMessages((list) => [...list, { id: nextId.current++, from: "notice", text: reply.notice! }]);
      setStatus(reply.status);
      setProgress({ asked: reply.questionsAsked, total: reply.questionsTotal });
      if (reply.question) addQuestion(reply.question);
    } catch (err) {
      setMessages((list) => list.filter((m) => m.id !== mine)); // gửi hỏng → bỏ bong bóng, nội dung còn ở ô gõ / Recorder
      setFailure(err);
      throw err;
    } finally {
      setBusy(false);
    }
  }

  async function sendVoice(audio: Blob) {
    setBusy(true);
    setFailure(undefined);
    let transcript: Schema<"Transcript">;
    try {
      const form = new FormData();
      form.append("file", audio, `turn.${audio.type.includes("mp4") ? "m4a" : audio.type.includes("ogg") ? "ogg" : "webm"}`);
      form.append("consent", String(consentRef.current)); // BR-13: chỉ lưu ghi âm khi SV đồng ý (C1-12)
      transcript = await apiCall("post", "/sessions/{session_id}/audio", { path: { session_id: sessionId }, body: form });
    } catch (err) {
      setFailure(err);
      setBusy(false);
      throw err;
    }
    if (!transcript.text.trim()) {
      const e = new NoSpeech();
      setFailure(e);
      setBusy(false);
      throw e;
    }
    if (transcript.needsConfirmation) {
      // SV-05: dừng lại cho SV kiểm tra bản chép lời trước khi gửi (FR-TB-06, 07)
      setPending({ transcript, audioUrl: URL.createObjectURL(audio) });
      setBusy(false);
      return;
    }
    await postTurn({
      inputMode: "VOICE",
      text: transcript.text,
      audioRef: transcript.audioRef,
      sttConfidence: transcript.confidence,
      transcriptEdited: false,
    });
  }

  function closePending() {
    if (pending?.audioUrl) URL.revokeObjectURL(pending.audioUrl);
    setPending(undefined);
  }

  async function confirmPending(text: string, edited: boolean) {
    if (!pending) return;
    const { transcript } = pending;
    closePending();
    await postTurn({ inputMode: "VOICE", text, audioRef: transcript.audioRef, sttConfidence: transcript.confidence, transcriptEdited: edited }).catch(() => {});
  }

  return (
    <div className="-m-4 flex min-h-[calc(100vh-8rem)] flex-col">
      <header className="space-y-2 bg-ink-900 px-4 py-3 text-white">
        <p className="caps text-ink-300">Giảng cho Whybi</p>
        <h1 className="text-h2 font-bold">{initial.nodeTitle ?? "Phiên giảng lại"}</h1>
        {progress.total > 0 && <Progress asked={progress.asked} total={progress.total} />}
      </header>

      <section role="log" aria-label="Hội thoại với Whybi" aria-live="polite" className="flex-1 space-y-4 px-4 py-4">
        {waiting && (
          <p role="status" className="flex items-center gap-2 text-body-m text-ink-500">
            <LoaderCircle aria-hidden size={16} className="animate-spin text-teal" /> Whybi đang chuẩn bị câu hỏi…
          </p>
        )}
        {noQuestion && gaveUp && (
          <p role="note" className="flex items-start gap-2 text-body-m text-ink-500">
            <Info aria-hidden size={16} className="mt-0.5 shrink-0 text-teal" /> Chưa tải lại được câu hỏi của Whybi. Bạn cứ giảng tiếp nhé.
          </p>
        )}
        {messages.map((m) => (
          <Bubble key={m.id} m={m} />
        ))}
      </section>

      <section aria-label="Khung trả lời" className="sticky bottom-16 space-y-3 border-t border-line-soft bg-surface px-4 py-3">
        {failure !== undefined && <FailureBox failure={failure} />}

        {pending && (
          <TranscriptConfirm transcript={pending.transcript} audioUrl={pending.audioUrl} busy={busy} onConfirm={confirmPending} onRetry={closePending} onCancel={closePending} />
        )}
        {live ? (
          <>
            <ModeTabs mode={mode} onChange={setMode} />
            <div role="tabpanel" id={`panel-${mode}`} aria-labelledby={`tab-${mode}`}>
              {mode === "VOICE" ? (
                <Recorder
                  key={turnType}
                  maxSeconds={turnType === "EXPLANATION" ? 180 : 90}
                  consented={consented}
                  onConsent={onConsent}
                  onSubmit={sendVoice}
                  onUseText={() => setMode("TEXT")}
                  disabled={busy || waiting}
                />
              ) : (
                <TextComposer turnType={turnType} busy={busy || waiting} onSend={(t) => postTurn({ inputMode: "TEXT", transcriptEdited: false, ...t })} />
              )}
            </div>
            <p className="flex items-start gap-2 rounded-md border border-honey/50 bg-honey-soft px-3 py-2 text-body-s text-honey-deep">
              <Info aria-hidden size={14} className="mt-0.5 shrink-0" />
              Hãy giải thích bản chất “vì sao”, không chỉ nêu định nghĩa. Whybi sẽ không đưa đáp án.
            </p>
          </>
        ) : (
          <Finished sessionId={sessionId} status={status} />
        )}
      </section>
    </div>
  );
}

/** Lỗi riêng: STT trả bản chép lời rỗng. */
class NoSpeech extends Error {}

function FailureBox({ failure }: { failure: unknown }) {
  if (failure instanceof ApiError && failure.notImplemented) return <DevelopingBox text={failure.message} />;
  if (failure instanceof NoSpeech) return <ErrorBox text="Whybi chưa nghe rõ lời bạn. Hãy ghi lại gần micro hơn, hoặc gõ chữ." />;
  return <ErrorBox text={errorText(failure)} />;
}

function Progress({ asked, total }: { asked: number; total: number }) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-body-s font-semibold">
        Câu phản biện {asked}/{total}
      </span>
      <span aria-hidden className="flex gap-1">
        {Array.from({ length: total }, (_, i) => (
          <span key={i} className={`h-1.5 w-5 rounded-full ${i < asked ? "bg-honey" : "bg-ink-700"}`} />
        ))}
      </span>
    </div>
  );
}

function Bubble({ m }: { m: Message }) {
  if (m.from === "notice")
    return (
      <p role="note" className="flex items-start gap-2 rounded-md border border-line-strong bg-st-grey px-3 py-2 text-body-s text-ink-700">
        <TriangleAlert aria-hidden size={14} className="mt-0.5 shrink-0" /> {m.text}
      </p>
    );
  if (m.from === "tutee")
    return (
      <div className="flex items-start gap-2">
        <Logo size={28} />
        <div className="max-w-[85%] space-y-1">
          <p className="caps text-honey-deep">Whybi · Học trò tò mò</p>
          <p className="whitespace-pre-wrap rounded-lg rounded-tl-sm border border-line-soft bg-surface px-3 py-2 text-body-m shadow-card">{m.text}</p>
        </div>
      </div>
    );
  return (
    <div className="ml-auto max-w-[85%] space-y-1 text-right">
      <p className="caps flex items-center justify-end gap-1 text-teal">
        {m.mode === "VOICE" ? <Mic aria-hidden size={12} /> : <Keyboard aria-hidden size={12} />}
        Bạn · {m.mode === "VOICE" ? "Giọng nói" : "Văn bản"}
      </p>
      <p className="whitespace-pre-wrap rounded-lg rounded-tr-sm bg-teal-soft px-3 py-2 text-left text-body-m">{m.text}</p>
    </div>
  );
}

function ModeTabs({ mode, onChange }: { mode: InputMode; onChange: (m: InputMode) => void }) {
  const tabs: { value: InputMode; label: string; icon: typeof Mic }[] = [
    { value: "VOICE", label: "Giọng nói", icon: Mic },
    { value: "TEXT", label: "Văn bản", icon: Keyboard },
  ];
  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const next: InputMode = mode === "VOICE" ? "TEXT" : "VOICE";
    onChange(next);
    e.currentTarget.querySelector<HTMLButtonElement>(`#tab-${next}`)?.focus();
  }
  return (
    <div role="tablist" aria-label="Cách giảng" className="grid grid-cols-2 gap-1 rounded-md bg-app p-1" onKeyDown={onKey}>
      {tabs.map(({ value, label, icon: Icon }) => {
        const selected = mode === value;
        return (
          <button
            key={value}
            id={`tab-${value}`}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={selected ? `panel-${value}` : undefined}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(value)}
            className={`flex items-center justify-center gap-2 rounded-md py-2 text-body-m font-semibold ${selected ? "bg-surface text-ink-900 shadow-card" : "text-ink-500"}`}
          >
            <Icon aria-hidden size={16} /> {label}
          </button>
        );
      })}
    </div>
  );
}

function TextComposer({
  turnType,
  busy,
  onSend,
}: {
  turnType: Turn["turnType"];
  busy: boolean;
  onSend: (t: { text: string; pasteRatio: number; typingCps: number }) => Promise<void>;
}) {
  const [text, setText] = useState("");
  const meter = useRef(createTypingMeter());
  // đổi lượt (giảng → trả lời) thì đo lại từ đầu
  useEffect(() => meter.current.reset(), [turnType]);

  const label = turnType === "EXPLANATION" ? "Lời giảng của bạn" : "Câu trả lời của bạn";
  const content = text.trim();

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    if (!content || busy) return;
    try {
      await onSend({ text: content, ...meter.current.snapshot() });
      setText("");
      meter.current.reset();
    } catch {
      /* lỗi đã hiện ở FailureBox; giữ chữ để gửi lại */
    }
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <label htmlFor="turn-text" className="sr-only">
        {label}
      </label>
      <textarea
        id="turn-text"
        value={text}
        rows={4}
        maxLength={MAX_TEXT}
        placeholder={turnType === "EXPLANATION" ? "Giảng lại khái niệm này bằng lời của bạn…" : "Trả lời câu hỏi của Whybi…"}
        onPaste={(e: ClipboardEvent<HTMLTextAreaElement>) => meter.current.paste(e.clipboardData?.getData("text")?.length ?? 0)}
        onChange={(e) => {
          meter.current.change(text, e.target.value);
          setText(e.target.value);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) void submit();
        }}
        className="w-full resize-y rounded-md border border-line-strong bg-surface px-3 py-2 text-body-m placeholder:text-ink-300 focus-visible:outline-2 focus-visible:outline-teal"
      />
      <div className="flex items-center justify-between gap-2">
        <span className="text-body-s text-ink-500">
          {text.length.toLocaleString("vi-VN")}/{MAX_TEXT.toLocaleString("vi-VN")} · Ctrl + Enter để gửi
        </span>
        <Button type="submit" variant="teal" disabled={!content || busy} aria-label={turnType === "EXPLANATION" ? "Gửi lời giảng" : "Gửi câu trả lời"}>
          {busy ? <LoaderCircle aria-hidden size={16} className="animate-spin" /> : <Send aria-hidden size={16} />} Gửi
        </Button>
      </div>
    </form>
  );
}

function Finished({ sessionId, status }: { sessionId: string; status: SessionStatus }) {
  const flagged = status === "FLAGGED" || status === "ABANDONED";
  return (
    <div role="status" className="space-y-3 rounded-lg border border-line-soft bg-app p-4">
      <p className="flex items-center gap-2 text-body-m font-semibold">
        {flagged ? <TriangleAlert aria-hidden size={18} className="text-honey-deep" /> : <CircleCheck aria-hidden size={18} className="text-teal" />}
        {flagged
          ? "Phiên đã dừng. Giảng viên sẽ xem lại phiên này."
          : status === "EVALUATING"
            ? "Bạn đã trả lời hết câu hỏi. Whybi đang chấm lời giảng…"
            : "Phiên đã hoàn tất."}
      </p>
      <Link
        to={`/sv/sessions/${sessionId}/result`}
        className="inline-flex items-center gap-2 rounded-md bg-teal px-4 py-2 text-body-m font-semibold text-white hover:brightness-110"
      >
        Xem kết quả
      </Link>
    </div>
  );
}
