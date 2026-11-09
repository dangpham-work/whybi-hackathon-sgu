import { CircleCheck, Info, Keyboard, LoaderCircle, Mic, Timer, TriangleAlert, Volume2, VolumeX } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useBeforeUnload, useBlocker, useLocation, useParams } from "react-router";
import { DevelopingBox, ErrorBox, LoadingBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { Logo } from "../../components/Logo";
import { TranscriptConfirm } from "../../components/TranscriptConfirm";
import { UnifiedChatComposer } from "../../components/UnifiedChatComposer";
import { ApiError, apiCall, errorText, FRIENDLY, type Schema } from "../../lib/api";
import { fetchAudioUrl } from "../../lib/audio";
import { mmss, useCountdown } from "../../lib/countdown";
import { useApi } from "../../lib/useApi";
import { useChannel } from "../../lib/ws";

type Question = Schema<"Question">;
type InputMode = Schema<"InputMode">;
type SessionStatus = Schema<"SessionStatus">;
type Turn = Schema<"Turn">;
type SessionTurnView = Schema<"SessionTurnView">;

/**
 * Dữ liệu SV-03 truyền sang khi bấm "Bắt đầu giảng" (GD-06):
 *   navigate(`/sv/sessions/${created.sessionId}`, { state: { opening: created.opening, nodeTitle, inputMode } })
 * Đây chỉ là dữ liệu hiện ngay cho nhanh: khi mở trang (kể cả tải lại) màn luôn gọi GET /sessions/{id} (C1-18, bug #153)
 * để lấy hội thoại, câu đang chờ kèm hạn, tiến độ và giai đoạn từ máy chủ; tên nút chỉ có ở đây (SessionState không trả).
 */
export interface SessionLocationState {
  opening?: Question;
  nodeTitle?: string;
  inputMode?: InputMode;
  status?: SessionStatus;
  /** SV bật đọc câu hỏi từ lúc bắt đầu (SessionStart.ttsEnabled). */
  ttsEnabled?: boolean;
}

type Message = { id: number; from: "tutee"; text: string } | { id: number; from: "student"; text: string; mode: InputMode } | { id: number; from: "notice"; text: string };

const LIVE: SessionStatus[] = ["CREATED", "EXPLAINING", "CHALLENGING"];
const OPENING_WAIT_MS = 6_000; // chờ câu mở đầu qua WebSocket tối đa chừng này rồi cho SV giảng tiếp

/** Vị trí tin cuối cùng của một bên (lib ES2022 chưa có findLastIndex). */
function lastIndexOf(list: Message[], from: Message["from"]) {
  for (let i = list.length - 1; i >= 0; i--) if (list[i].from === from) return i;
  return -1;
}

/** Một lượt đã lưu trên máy chủ → bong bóng hội thoại. */
function toMessage(t: SessionTurnView, id: number): Message {
  if (t.turnType === "SYSTEM_NOTICE") return { id, from: "notice", text: t.text };
  if (t.speaker === "TUTEE") return { id, from: "tutee", text: t.text };
  return { id, from: "student", text: t.text, mode: t.inputMode };
}

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
  const [deadline, setDeadline] = useState<string | null>(initial.opening?.deadline ?? null);
  const [tts, setTts] = useState(initial.ttsEnabled ?? false);
  const ttsRef = useRef(tts);
  ttsRef.current = tts;
  const audioCleanup = useRef<(() => void) | undefined>(undefined);
  const audioRequest = useRef(0);
  const lastAudioUrl = useRef<string | undefined>(undefined);
  const stopSpeech = useCallback(() => {
    audioRequest.current++;
    audioCleanup.current?.();
    audioCleanup.current = undefined;
  }, []);

  // Khôi phục phiên từ máy chủ khi mở trang (bug #153): F5 giữa phản biện không mất hội thoại, hạn trả lời, tiến độ.
  const restore = useApi((signal) => apiCall("get", "/sessions/{session_id}", { path: { session_id: sessionId }, signal }), [sessionId]);
  // SV đã gửi lượt ở màn này thì không ghi đè hội thoại bằng bản tải về muộn (bản đó cũ hơn).
  const touched = useRef(false);
  useEffect(() => {
    const s = restore.data;
    if (!s || touched.current) return;
    setMessages(s.turns.map((t) => toMessage(t, nextId.current++)));
    setStatus(s.status);
    setProgress({ asked: s.questionsAsked, total: s.questionsTotal });
    // Thời gian trả lời tính từ lúc SV thấy lại câu hỏi; hạn thật vẫn do máy chủ giữ (deadline).
    askedAt.current = Date.now();
    setDeadline(s.question?.deadline ?? null);
    if (initial.ttsEnabled === undefined) setTts(s.ttsEnabled);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restore.data]);
  const restoring = restore.status === "loading" && !restore.data;

  const turnType: Turn["turnType"] = status === "CHALLENGING" ? "ANSWER" : "EXPLANATION";
  const live = LIVE.includes(status);

  // Thoát khi đang làm bài (đóng/tải lại tab, điều hướng trong app qua thanh tab dưới…) ⇒ cảnh báo mất ghi âm/nội dung chưa gửi.
  useBeforeUnload(
    useCallback(
      (e: BeforeUnloadEvent) => {
        if (!live) return;
        e.preventDefault();
        e.returnValue = "";
      },
      [live],
    ),
  );
  const blocker = useBlocker(live);
  const noQuestion = live && !messages.some((m) => m.from === "tutee");
  // Đang tải phiên mà chưa có gì để hiện ⇒ khóa ô trả lời; tải xong vẫn chưa có câu hỏi (câu mở đầu còn đang sinh)
  // hoặc tải lỗi ⇒ chờ kênh session:{id} một lúc rồi mở khóa ô trả lời.
  const loadingBlank = restoring && messages.length === 0;
  const [gaveUp, setGaveUp] = useState(false);
  useEffect(() => {
    if (!noQuestion || restoring) return;
    const t = setTimeout(() => setGaveUp(true), OPENING_WAIT_MS);
    return () => clearTimeout(t);
  }, [noQuestion, restoring]);
  const waiting = (noQuestion && !gaveUp && !restoring) || loadingBlank;

  /** Thêm câu hỏi của Whybi, bỏ trùng (cùng câu có thể tới từ TurnReply và từ WebSocket). */
  const addQuestion = useCallback((q: Question) => {
    setMessages((list) => {
      const lastTutee = lastIndexOf(list, "tutee");
      // câu này đã hiện và SV chưa trả lời → bỏ qua bản trùng
      if (lastTutee >= 0 && lastTutee > lastIndexOf(list, "student") && list[lastTutee].text === q.text) return list;
      return [...list, { id: nextId.current++, from: "tutee", text: q.text }];
    });
    askedAt.current = Date.now();
    setDeadline(q.deadline ?? null);
    if (ttsRef.current && q.audioUrl && lastAudioUrl.current !== q.audioUrl) {
      lastAudioUrl.current = q.audioUrl;
      void speak(q.audioUrl);
    }
  }, []);

  /** Đọc câu hỏi (FR-TB-10): tải âm thanh bằng token rồi phát; lỗi thì bỏ qua, phiên vẫn chạy bình thường. */
  async function speak(audioUrl: string) {
    stopSpeech();
    const request = audioRequest.current;
    let release: (() => void) | undefined;
    try {
      const url = await fetchAudioUrl(audioUrl);
      if (!ttsRef.current || request !== audioRequest.current) {
        URL.revokeObjectURL(url);
        return;
      }
      let released = false;
      let el: HTMLAudioElement | undefined;
      release = () => {
        if (released) return;
        released = true;
        el?.pause();
        URL.revokeObjectURL(url);
      };
      audioCleanup.current = release;
      el = new Audio(url);
      el.onended = release;
      el.onerror = release;
      await el.play();
    } catch {
      release?.();
      /* TTS hỏng không được làm hỏng phiên */
    }
  }
  useEffect(() => {
    if (!tts) stopSpeech();
    return stopSpeech;
  }, [tts, stopSpeech]);

  useChannel(sessionId ? `session:${sessionId}` : null, (e) => {
    if (e.event === "session.question" && e.payload && typeof (e.payload as Question).text === "string") addQuestion(e.payload as Question);
  });

  function applyReply(reply: Schema<"TurnReply">) {
    if (reply.notice) setMessages((list) => [...list, { id: nextId.current++, from: "notice", text: reply.notice! }]);
    setStatus(reply.status);
    setProgress({ asked: reply.questionsAsked, total: reply.questionsTotal });
    if (reply.question) addQuestion(reply.question);
    else setDeadline(null);
  }

  /** Hết giờ trả lời: báo máy chủ tính câu này là chưa trả lời và sang câu kế (FR-TB-11). */
  const seconds = useCountdown(deadline);
  const timedOut = useRef<string | null>(null);
  useEffect(() => {
    if (seconds !== 0 || !deadline || timedOut.current === deadline || !live || busy) return;
    timedOut.current = deadline; // mỗi câu chỉ báo một lần
    apiCall("post", "/sessions/{session_id}/timeout", { path: { session_id: sessionId } }).then(applyReply, setFailure);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seconds, deadline, busy, live, sessionId]);

  /** Tự động cuộn tới tin nhắn mới nhất trong hội thoại */
  const messagesEndRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [messages, waiting, failure]);

  /** Gửi một lượt; ném lỗi lại để ô gõ / Recorder giữ nội dung cho lần gửi lại. */
  async function postTurn(turn: Omit<Turn, "turnType" | "responseTimeMs">) {
    touched.current = true;
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
      applyReply(reply);
    } catch (err) {
      setMessages((list) => list.filter((m) => m.id !== mine)); // gửi hỏng → bỏ bong bóng, nội dung còn ở ô gõ / Recorder
      setFailure(err);
      throw err;
    } finally {
      setBusy(false);
    }
  }

  async function handleUnifiedSend(payload: {
    text: string;
    inputMode: InputMode;
    audioBlob?: Blob;
    durationMs?: number;
    pasteRatio: number;
    typingCps: number;
  }) {
    let audioRef: string | undefined;
    let sttConfidence: number | undefined;
    let transcriptEdited = false;

    let textToSend = payload.text.trim();
    if (payload.audioBlob && payload.inputMode === "VOICE") {
      try {
        const form = new FormData();
        const ext = payload.audioBlob.type.includes("mp4") ? "m4a" : payload.audioBlob.type.includes("ogg") ? "ogg" : "webm";
        form.append("file", payload.audioBlob, `turn.${ext}`);
        form.append("consent", String(consentRef.current));
        const transcript = await apiCall("post", "/sessions/{session_id}/audio", {
          path: { session_id: sessionId },
          body: form,
        });

        if (!transcript.text.trim() && !textToSend) {
          const e = new NoSpeech();
          setFailure(e);
          throw e;
        }

        if (transcript.needsConfirmation) {
          setPending({ transcript, audioUrl: URL.createObjectURL(payload.audioBlob) });
          return;
        }

        audioRef = transcript.audioRef;
        sttConfidence = transcript.confidence;
        if (!textToSend) {
          textToSend = transcript.text;
          transcriptEdited = false;
        } else {
          transcriptEdited = textToSend !== transcript.text.trim();
        }
      } catch (err) {
        if (!textToSend) {
          setFailure(err);
          throw err;
        }
      }
    }

    await postTurn({
      inputMode: payload.inputMode,
      text: textToSend,
      audioRef,
      sttConfidence,
      transcriptEdited,
      pasteRatio: payload.pasteRatio,
      typingCps: payload.typingCps,
    });
  }

  async function handleTranscribeAudio(audio: Blob): Promise<string> {
    const form = new FormData();
    const ext = audio.type.includes("mp4") ? "m4a" : audio.type.includes("ogg") ? "ogg" : "webm";
    form.append("file", audio, `turn.${ext}`);
    form.append("consent", String(consentRef.current));
    const transcript = await apiCall("post", "/sessions/{session_id}/audio", {
      path: { session_id: sessionId },
      body: form,
    });
    return transcript.text;
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
        <div className="flex flex-wrap items-center justify-between gap-2">
          {progress.total > 0 ? <Progress asked={progress.asked} total={progress.total} /> : <span />}
          <div className="flex items-center gap-2">
            {live && seconds !== null && (
              <span role="timer" aria-label={`Còn ${seconds} giây để trả lời`} className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-body-s font-bold ${seconds <= 15 ? "bg-red-600 text-white" : "bg-ink-700 text-white"}`}>
                <Timer aria-hidden size={14} /> {mmss(seconds)}
              </span>
            )}
            <button
              type="button"
              aria-pressed={tts}
              onClick={() => setTts((v) => !v)}
              className="inline-flex items-center gap-1 rounded-full bg-ink-700 px-3 py-1 text-body-s font-semibold text-white"
            >
              {tts ? <Volume2 aria-hidden size={14} /> : <VolumeX aria-hidden size={14} />} {tts ? "Đang đọc câu hỏi" : "Đọc câu hỏi"}
            </button>
          </div>
        </div>
      </header>

      <section role="log" aria-label="Hội thoại với Whybi" aria-live="polite" className="flex-1 space-y-4 px-4 py-4">
        {loadingBlank && <LoadingBox text="Đang tải lại phiên…" />}
        {restore.status === "error" && <RestoreError error={restore.error} onRetry={restore.reload} />}
        {waiting && !loadingBlank && (
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
        <div ref={messagesEndRef} />
      </section>

      <section aria-label="Khung trả lời" className="sticky bottom-16 space-y-2 border-t border-line-soft bg-surface/95 px-3 py-2 backdrop-blur-sm">
        {failure !== undefined && <FailureBox failure={failure} />}

        {pending && (
          <TranscriptConfirm transcript={pending.transcript} audioUrl={pending.audioUrl} busy={busy} onConfirm={confirmPending} onRetry={closePending} onCancel={closePending} />
        )}
        {live ? (
          <>
            <UnifiedChatComposer
              turnType={turnType}
              maxSeconds={turnType === "EXPLANATION" ? 300 : 90}
              consented={consented}
              onConsent={onConsent}
              busy={busy || waiting}
              disabled={busy || waiting}
              onSend={handleUnifiedSend}
              onTranscribeAudio={handleTranscribeAudio}
            />
            <p className="text-center text-[11px] text-ink-500">
              <span className="font-semibold text-honey-deep">Mẹo:</span> Hãy giải thích bản chất “vì sao”, không chỉ nêu định nghĩa. Whybi sẽ không đưa đáp án.
            </p>
          </>
        ) : (
          <Finished sessionId={sessionId} status={status} />
        )}
      </section>

      {blocker.state === "blocked" && <LeaveSessionDialog onStay={() => blocker.reset()} onLeave={() => blocker.proceed()} />}
    </div>
  );
}

/** Thoát phiên đang làm: xác nhận trước khi điều hướng đi, vì ghi âm/nội dung chưa gửi và kết quả phiên sẽ không được lưu. */
function LeaveSessionDialog({ onStay, onLeave }: { onStay: () => void; onLeave: () => void }) {
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="leave-title" aria-describedby="leave-desc" className="fixed inset-0 z-30 flex items-end justify-center bg-ink-900/40 p-4 sm:items-center">
      <div className="w-full max-w-sm space-y-3 rounded-xl bg-surface p-5 shadow-dialog">
        <h2 id="leave-title" className="flex items-center gap-2 text-h3 font-semibold">
          <TriangleAlert aria-hidden size={20} className="text-honey-deep" /> Thoát phiên giảng?
        </h2>
        <p id="leave-desc" className="text-body-m text-ink-700">
          Bạn đang giảng bài. Nếu thoát ra bây giờ, ghi âm hoặc nội dung chưa gửi và kết quả của phiên này sẽ không được lưu.
        </p>
        <div className="flex flex-col gap-2 sm:flex-row-reverse">
          <Button variant="secondary" className="flex-1" onClick={onLeave}>
            Thoát, không lưu
          </Button>
          <Button variant="teal" className="flex-1" onClick={onStay}>
            Tiếp tục làm bài
          </Button>
        </div>
      </div>
    </div>
  );
}

/** Không tải được trạng thái phiên: báo rõ, cho thử lại; màn vẫn dùng dữ liệu đang có (location state / WebSocket). */
function RestoreError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  if (error instanceof ApiError && error.notImplemented) return <DevelopingBox text={error.message} />;
  if (error instanceof ApiError && error.status === 401) return <ErrorBox text={error.message} loginAgain />;
  return <ErrorBox text={`Chưa tải lại được phiên: ${errorText(error)}`} onRetry={onRetry} />;
}

/** Lỗi riêng: STT trả 200 nhưng bản chép lời rỗng (backend thường trả 422 NO_SPEECH_DETECTED – cùng câu, xem FRIENDLY). */
class NoSpeech extends Error {}

function FailureBox({ failure }: { failure: unknown }) {
  if (failure instanceof ApiError && failure.notImplemented) return <DevelopingBox text={failure.message} />;
  if (failure instanceof NoSpeech) return <ErrorBox text={FRIENDLY.NO_SPEECH_DETECTED} />;
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
