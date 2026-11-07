import { Keyboard, LoaderCircle, Mic, MicOff, RotateCcw, Send, ShieldCheck, Square, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { Button } from "./Button";
import { Waveform } from "./Waveform";

type Phase = "idle" | "asking" | "starting" | "recording" | "recorded" | "sending" | "denied" | "unsupported" | "failed";

const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];

/** mm:ss */
export const clockText = (sec: number) => `${String(Math.floor(sec / 60)).padStart(2, "0")}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;

function pickMime(): string | undefined {
  const isSupported = (MediaRecorder as { isTypeSupported?: (t: string) => boolean }).isTypeSupported;
  return isSupported ? MIME_CANDIDATES.find((t) => isSupported(t)) : undefined;
}

export interface RecorderProps {
  /** Giới hạn ghi: 180 s cho lời giảng, 90 s cho câu trả lời (FR-TB-05). Hết giờ tự dừng. */
  maxSeconds?: number;
  /** SV đã đồng ý ghi âm chưa (BR-13) – bên dùng giữ để chỉ hỏi một lần. */
  consented: boolean;
  onConsent: (agreed: boolean) => void;
  /** Gửi bản ghi. Ném lỗi thì giữ bản ghi để gửi lại; bên dùng tự hiện lỗi. */
  onSubmit: (audio: Blob, durationMs: number) => Promise<void>;
  /** Luôn có đường chuyển sang gõ văn bản (6.4 đề cương). */
  onUseText: () => void;
  disabled?: boolean;
}

/**
 * Recorder – ghi âm MediaRecorder (webm/opus), ≤ 3 phút lời giảng / 90 giây câu trả lời,
 * hỏi đồng ý trước lần đầu (BR-13) và chỉ xin micro sau khi SV đồng ý. Thẻ: GD-07 (Thắng).
 * Giao diện theo Figma SV-04: nút tròn đỏ "Đang ghi", Waveform, mm:ss / 03:00, "Ghi lại", "Gửi".
 */
export function Recorder({ maxSeconds = 180, consented, onConsent, onSubmit, onUseText, disabled }: RecorderProps) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [elapsed, setElapsed] = useState(0);
  const [stream, setStream] = useState<MediaStream>();
  const [autoStopped, setAutoStopped] = useState(false);
  const rec = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const audio = useRef<{ blob: Blob; ms: number } | null>(null);
  const startedAt = useRef(0);
  const timers = useRef<{ tick?: ReturnType<typeof setInterval>; limit?: ReturnType<typeof setTimeout> }>({});
  const sendWhenStopped = useRef(false);
  const mounted = useRef(true);

  const clearTimers = () => {
    clearInterval(timers.current.tick);
    clearTimeout(timers.current.limit);
    timers.current = {};
  };
  const releaseMic = (s?: MediaStream) => s?.getTracks().forEach((t) => t.stop());

  // Rời màn khi đang ghi: dừng ghi, trả micro, không gửi gì.
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      clearTimers();
      const r = rec.current;
      if (r) {
        r.ondataavailable = null;
        r.onstop = null;
        if (r.state !== "inactive") r.stop();
        releaseMic(r.stream);
      }
    };
  }, []);

  async function send(blob: Blob, ms: number) {
    setPhase("sending");
    try {
      await onSubmit(blob, ms);
      if (!mounted.current) return;
      audio.current = null;
      setElapsed(0);
      setAutoStopped(false);
      setPhase("idle");
    } catch {
      if (mounted.current) setPhase("recorded"); // giữ bản ghi để bấm Gửi lại
    }
  }

  async function begin() {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setPhase("unsupported");
      return;
    }
    setPhase("starting");
    let s: MediaStream;
    try {
      s = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      const name = e instanceof DOMException ? e.name : "";
      setPhase(name === "NotAllowedError" || name === "SecurityError" ? "denied" : "failed");
      return;
    }
    if (!mounted.current) return releaseMic(s);

    let mimeType: string | undefined;
    let r: MediaRecorder;
    try {
      mimeType = pickMime();
      r = new MediaRecorder(s, mimeType ? { mimeType } : undefined);
      r.start(1000); // sự kiện dữ liệu được phát bất đồng bộ sau tác vụ hiện tại
    } catch {
      releaseMic(s);
      setPhase("failed");
      return;
    }
    rec.current = r;
    chunks.current = [];
    audio.current = null;
    sendWhenStopped.current = false;
    r.ondataavailable = (e: BlobEvent) => {
      if (e.data && e.data.size > 0) chunks.current.push(e.data);
    };
    r.onstop = () => {
      clearTimers();
      releaseMic(s);
      setStream(undefined);
      const ms = Math.min(Date.now() - startedAt.current, maxSeconds * 1000);
      const blob = new Blob(chunks.current, { type: r.mimeType || mimeType || "audio/webm" });
      audio.current = { blob, ms };
      setElapsed(ms / 1000);
      if (sendWhenStopped.current) void send(blob, ms);
      else setPhase("recorded");
    };

    startedAt.current = Date.now();
    setElapsed(0);
    setAutoStopped(false);
    setStream(s);
    setPhase("recording");
    timers.current.tick = setInterval(() => setElapsed(Math.min((Date.now() - startedAt.current) / 1000, maxSeconds)), 250);
    timers.current.limit = setTimeout(() => {
      setAutoStopped(true);
      setElapsed(maxSeconds);
      stop();
    }, maxSeconds * 1000);
  }

  function stop() {
    const r = rec.current;
    if (r && r.state !== "inactive") r.stop();
  }

  function start() {
    if (disabled) return;
    if (!consented) return setPhase("asking");
    void begin();
  }

  function agree(ok: boolean) {
    onConsent(ok);
    if (ok) void begin();
    else {
      setPhase("idle");
      onUseText();
    }
  }

  function retake() {
    sendWhenStopped.current = false;
    const r = rec.current;
    if (r) {
      r.ondataavailable = null;
      r.onstop = null; // bỏ bản đang ghi
      if (r.state !== "inactive") r.stop();
      releaseMic(r.stream);
      rec.current = null;
      clearTimers();
      setStream(undefined);
    }
    audio.current = null;
    setElapsed(0);
    setAutoStopped(false);
    setPhase("idle");
  }

  function submit() {
    if (phase === "recording") {
      sendWhenStopped.current = true;
      setPhase("sending"); // khóa thao tác ngay cả khi trình duyệt chưa phát onstop
      stop();
    } else if (audio.current) {
      void send(audio.current.blob, audio.current.ms);
    }
  }

  if (phase === "denied" || phase === "unsupported" || phase === "failed") {
    const text =
      phase === "denied"
        ? "Trình duyệt không cho phép dùng micro. Bật quyền micro cho trang này trong cài đặt trình duyệt, hoặc gõ chữ thay thế."
        : phase === "unsupported"
          ? "Trình duyệt này chưa hỗ trợ ghi âm. Hãy gõ chữ, hoặc mở bằng Chrome / Edge / Safari bản mới."
          : "Không mở được micro (có thể đang được ứng dụng khác dùng). Thử lại hoặc gõ chữ.";
    return (
      <div role="alert" className="space-y-3 rounded-lg border border-red-700/40 bg-st-fail/40 p-4 text-body-m text-red-900">
        <p className="flex items-start gap-2">
          <MicOff aria-hidden size={18} className="mt-0.5 shrink-0" />
          {text}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={onUseText}>
            <Keyboard aria-hidden size={16} /> Chuyển sang gõ chữ
          </Button>
          {phase !== "unsupported" && (
            <Button variant="ghost" onClick={() => setPhase("idle")}>
              <RotateCcw aria-hidden size={16} /> Thử lại
            </Button>
          )}
        </div>
      </div>
    );
  }

  const recording = phase === "recording";
  const hasAudio = recording || phase === "recorded" || phase === "sending";
  const busy = phase === "starting" || phase === "sending" || disabled;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-4">
        <div className="flex shrink-0 flex-col items-center gap-1">
          {recording ? (
            <button
              type="button"
              onClick={stop}
              aria-label="Dừng ghi âm"
              className="flex size-16 items-center justify-center rounded-full bg-red-600 text-white shadow-float hover:bg-red-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-700"
            >
              <Square aria-hidden size={22} fill="currentColor" />
            </button>
          ) : (
            <button
              type="button"
              onClick={start}
              disabled={busy || phase === "recorded"}
              aria-label="Bắt đầu ghi âm"
              className="flex size-16 items-center justify-center rounded-full bg-teal text-white shadow-float hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal disabled:opacity-50"
            >
              {phase === "starting" ? <LoaderCircle aria-hidden size={24} className="animate-spin" /> : <Mic aria-hidden size={24} />}
            </button>
          )}
          {/* trạng thái luôn có chữ, không chỉ dựa vào màu đỏ (NFR-12) */}
          <span className={`text-body-s font-semibold ${recording ? "text-red-700" : "text-ink-500"}`}>
            {recording ? "Đang ghi" : phase === "recorded" ? "Đã dừng" : phase === "sending" ? "Đang gửi" : "Nhấn để ghi"}
          </span>
        </div>

        <div className="min-w-0 flex-1 space-y-1">
          <Waveform stream={stream} active={recording} />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-body-m font-semibold tabular-nums" aria-live="off">
              {clockText(elapsed)} / {clockText(maxSeconds)}
            </span>
            {hasAudio && (
              <span className="flex items-center gap-1">
                <Button variant="ghost" className="px-2 py-1" onClick={retake} disabled={phase === "sending"}>
                  <RotateCcw aria-hidden size={14} /> Ghi lại
                </Button>
                <Button variant="ghost" className="px-2 py-1 text-teal" onClick={submit} disabled={phase === "sending"} aria-label="Gửi bản ghi">
                  {phase === "sending" ? <LoaderCircle aria-hidden size={14} className="animate-spin" /> : <Send aria-hidden size={14} />} Gửi
                </Button>
              </span>
            )}
          </div>
        </div>
      </div>

      {autoStopped && phase === "recorded" && (
        <p role="status" className="flex items-center gap-2 text-body-s text-honey-deep">
          <TriangleAlert aria-hidden size={14} /> Đã đủ {Math.round(maxSeconds / 60)} phút – bản ghi tự dừng. Bấm Gửi hoặc Ghi lại.
        </p>
      )}

      {phase === "asking" && <ConsentDialog onAnswer={agree} />}
    </div>
  );
}

/** Hộp đồng ý ghi âm (BR-13) – hiện trước khi trình duyệt xin quyền micro. */
function ConsentDialog({ onAnswer }: { onAnswer: (ok: boolean) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // tiêu điểm mặc định ở lựa chọn an toàn ("Không") – đồng ý ghi âm phải là hành động chủ động (BR-13)
    const buttons = ref.current?.querySelectorAll<HTMLButtonElement>("button");
    buttons?.[buttons.length - 1]?.focus();
  }, []);
  // giữ phím Tab trong hộp thoại
  function trap(e: ReactKeyboardEvent) {
    if (e.key === "Escape") return onAnswer(false);
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
        aria-labelledby="consent-title"
        aria-describedby="consent-desc"
        onKeyDown={trap}
        className="w-full max-w-sm space-y-3 rounded-xl bg-surface p-5 shadow-dialog"
      >
        <h2 id="consent-title" className="flex items-center gap-2 text-h3 font-semibold">
          <ShieldCheck aria-hidden size={20} className="text-teal" /> Cho phép ghi âm lời giảng?
        </h2>
        <div id="consent-desc" className="space-y-2 text-body-m text-ink-700">
          <p>Whybi sẽ ghi âm giọng bạn (tối đa 3 phút mỗi lượt) để chuyển thành chữ và chấm lời giảng.</p>
          <p>Bản ghi chỉ dùng cho phiên học này và tự xóa sau thời hạn lưu trữ. Bạn luôn có thể gõ chữ thay vì nói.</p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row-reverse">
          <Button variant="teal" className="flex-1" onClick={() => onAnswer(true)}>
            <Mic aria-hidden size={16} /> Đồng ý ghi âm
          </Button>
          <Button variant="secondary" className="flex-1" onClick={() => onAnswer(false)}>
            <Keyboard aria-hidden size={16} /> Không, tôi sẽ gõ chữ
          </Button>
        </div>
      </div>
    </div>
  );
}
