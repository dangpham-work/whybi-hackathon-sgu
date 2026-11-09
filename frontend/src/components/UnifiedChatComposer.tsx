import { CornerDownLeft, LoaderCircle, Mic, RotateCcw, ShieldCheck, Square, TriangleAlert } from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ClipboardEvent,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { Button } from "./Button";
import { Waveform } from "./Waveform";
import { createTypingMeter } from "../lib/typing-meter";
import type { Schema } from "../lib/api";

type Turn = Schema<"Turn">;
type InputMode = Schema<"InputMode">;

export const MAX_TEXT = 20_000;

/** Định dạng mm:ss */
export const clockText = (sec: number) =>
  `${String(Math.floor(sec / 60)).padStart(2, "0")}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;

const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];

function pickMime(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  const isSupported = (MediaRecorder as { isTypeSupported?: (t: string) => boolean }).isTypeSupported;
  return isSupported ? MIME_CANDIDATES.find((t) => isSupported(t)) : undefined;
}

// Định nghĩa types cho Web Speech API
interface SpeechRecognitionErrorEvent extends Event {
  error: string;
  message?: string;
}

interface SpeechRecognitionEvent extends Event {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: {
      isFinal: boolean;
      length: number;
      [index: number]: {
        transcript: string;
        confidence: number;
      };
    };
  };
}

interface SpeechRecognitionInstance extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionInstance;

const getSpeechRecognition = (): SpeechRecognitionConstructor | undefined => {
  if (typeof window === "undefined") return undefined;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition;
};

export interface UnifiedChatComposerProps {
  turnType: Turn["turnType"];
  maxSeconds?: number;
  consented: boolean;
  onConsent: (agreed: boolean) => void;
  busy: boolean;
  disabled?: boolean;
  onSend: (payload: {
    text: string;
    inputMode: InputMode;
    audioBlob?: Blob;
    durationMs?: number;
    pasteRatio: number;
    typingCps: number;
  }) => Promise<void>;
  /** Fallback STT từ file audio khi Web Speech API không khả dụng */
  onTranscribeAudio?: (audioBlob: Blob) => Promise<string>;
}

export function UnifiedChatComposer({
  turnType,
  maxSeconds = turnType === "EXPLANATION" ? 300 : 90,
  consented,
  onConsent,
  busy,
  disabled,
  onSend,
  onTranscribeAudio,
}: UnifiedChatComposerProps) {
  const [text, setText] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [isRecorded, setIsRecorded] = useState(false);
  const [autoStopped, setAutoStopped] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [stream, setStream] = useState<MediaStream>();
  const [showConsent, setShowConsent] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<InputMode>("VOICE");

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const meter = useRef(createTypingMeter());
  const hasSpokenRef = useRef(false);
  const baseTextRef = useRef("");
  const currentSpeechRef = useRef("");
  const recordedAudioRef = useRef<{ blob: Blob; ms: number } | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef(0);
  const tickTimerRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const limitTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const mountedRef = useRef(true);
  const pendingSendRef = useRef(false);

  // Khi chuyển lượt thì reset meter
  useEffect(() => {
    meter.current.reset();
  }, [turnType]);

  const clearTimers = () => {
    if (tickTimerRef.current) clearInterval(tickTimerRef.current);
    if (limitTimerRef.current) clearTimeout(limitTimerRef.current);
    tickTimerRef.current = undefined;
    limitTimerRef.current = undefined;
  };

  const releaseMic = (s?: MediaStream) => {
    s?.getTracks().forEach((t) => t.stop());
  };

  const adjustTextareaHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const maxHeight = 220; // Tối đa ~8-9 dòng
    const nextHeight = Math.min(el.scrollHeight, maxHeight);
    el.style.height = `${Math.max(nextHeight, 64)}px`;
    el.scrollTop = el.scrollHeight; // Luôn cuộn tới dòng mới nhất
  }, []);

  // Cuộn và chỉnh kích thước khi text đổi
  useEffect(() => {
    adjustTextareaHeight();
  }, [text, adjustTextareaHeight]);

  // Dọn dẹp khi unmount
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearTimers();
      if (recognitionRef.current) {
        recognitionRef.current.onresult = null;
        recognitionRef.current.onerror = null;
        recognitionRef.current.onend = null;
        try {
          recognitionRef.current.abort();
        } catch {
          /* noop */
        }
      }
      const rec = mediaRecorderRef.current;
      if (rec) {
        rec.ondataavailable = null;
        rec.onstop = null;
        if (rec.state !== "inactive") rec.stop();
        releaseMic(rec.stream);
      }
    };
  }, []);

  const executeSend = async (blob?: Blob, durationMs?: number) => {
    const content = text.trim();
    // Nếu chưa có text trong ô nhưng có audio blob (như test gửi âm thanh để STT xử lý)
    const effectiveContent = content || (hasSpokenRef.current ? "..." : "");
    if (!effectiveContent && !blob) return;

    try {
      await onSend({
        text: content,
        inputMode: hasSpokenRef.current ? "VOICE" : "TEXT",
        audioBlob: blob ?? recordedAudioRef.current?.blob,
        durationMs: durationMs ?? recordedAudioRef.current?.ms,
        ...meter.current.snapshot(),
      });
      if (!mountedRef.current) return;
      setText("");
      baseTextRef.current = "";
      currentSpeechRef.current = "";
      hasSpokenRef.current = false;
      recordedAudioRef.current = null;
      setIsRecorded(false);
      setAutoStopped(false);
      setElapsed(0);
      meter.current.reset();
    } catch {
      /* Giữ nguyên text để người dùng gửi lại */
    }
  };

  const stopRecording = useCallback(() => {
    clearTimers();
    setIsRecording(false);

    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        /* noop */
      }
    }

    const rec = mediaRecorderRef.current;
    if (rec && rec.state !== "inactive") {
      rec.stop();
    }
  }, []);

  const startRecordingSession = async () => {
    setMicError(null);
    setAutoStopped(false);
    if (!navigator.mediaDevices?.getUserMedia) {
      setMicError("Trình duyệt này chưa hỗ trợ ghi âm. Hãy gõ chữ, hoặc mở bằng Chrome / Edge / Safari bản mới.");
      return;
    }

    let s: MediaStream;
    try {
      s = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      const name = e instanceof DOMException ? e.name : "";
      if (name === "NotAllowedError" || name === "SecurityError") {
        setMicError("Trình duyệt không cho phép dùng micro. Bật quyền micro cho trang này trong cài đặt trình duyệt, hoặc gõ chữ thay thế.");
      } else {
        setMicError("Không mở được micro (có thể đang được ứng dụng khác dùng). Thử lại hoặc gõ chữ.");
      }
      return;
    }

    if (!mountedRef.current) {
      releaseMic(s);
      return;
    }

    setStream(s);
    hasSpokenRef.current = true;
    baseTextRef.current = text.trim();
    currentSpeechRef.current = "";

    // 1. Khởi động Web Speech API nếu trình duyệt hỗ trợ
    const SR = getSpeechRecognition();
    let recognitionActive = false;
    if (SR) {
      try {
        const recognition = new SR();
        recognition.lang = "vi-VN";
        recognition.continuous = true;
        recognition.interimResults = true;

        recognition.onresult = (event: SpeechRecognitionEvent) => {
          let interim = "";
          let final = "";
          for (let i = 0; i < event.results.length; ++i) {
            const result = event.results[i];
            if (result.isFinal) {
              final += result[0].transcript + " ";
            } else {
              interim += result[0].transcript;
            }
          }
          const spoken = (final + interim).trim();
          currentSpeechRef.current = spoken;

          const base = baseTextRef.current;
          const combined = base ? `${base} ${spoken}` : spoken;
          setText(combined);
        };

        recognition.onerror = () => {
          /* Fallback bằng audio ghi âm */
        };

        recognition.onend = () => {
          baseTextRef.current = text.trim();
        };

        recognition.start();
        recognitionRef.current = recognition;
        recognitionActive = true;
      } catch {
        recognitionActive = false;
      }
    }

    // 2. Khởi động MediaRecorder
    let mimeType: string | undefined;
    let rec: MediaRecorder | null = null;
    try {
      mimeType = pickMime();
      rec = new MediaRecorder(s, mimeType ? { mimeType } : undefined);
    } catch {
      /* MediaRecorder không hỗ trợ định dạng */
    }

    chunksRef.current = [];
    if (rec) {
      rec.ondataavailable = (e: BlobEvent) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.onstop = async () => {
        clearTimers();
        releaseMic(s);
        setStream(undefined);
        const ms = Math.min(Date.now() - startedAtRef.current, maxSeconds * 1000);
        const blob = new Blob(chunksRef.current, { type: rec?.mimeType || mimeType || "audio/webm" });
        recordedAudioRef.current = { blob, ms };
        setElapsed(ms / 1000);
        setIsRecorded(true);

        if (pendingSendRef.current) {
          pendingSendRef.current = false;
          void executeSend(blob, ms);
          return;
        }

        // Nếu Web Speech API không hoạt động và có handler transcribe
        if (!recognitionActive && onTranscribeAudio && blob.size > 0) {
          try {
            const transcript = await onTranscribeAudio(blob);
            if (transcript) {
              const base = baseTextRef.current;
              const nextVal = base ? `${base} ${transcript}` : transcript;
              setText(nextVal);
              baseTextRef.current = nextVal;
            }
          } catch {
            /* lỗi transcribe */
          }
        } else {
          baseTextRef.current = text.trim();
        }
      };

      mediaRecorderRef.current = rec;
      rec.start(1000);
    }

    startedAtRef.current = Date.now();
    setElapsed(0);
    setIsRecording(true);
    setIsRecorded(false);

    clearTimers();
    tickTimerRef.current = setInterval(() => {
      setElapsed(Math.min((Date.now() - startedAtRef.current) / 1000, maxSeconds));
    }, 250);

    limitTimerRef.current = setTimeout(() => {
      setAutoStopped(true);
      setElapsed(maxSeconds);
      stopRecording();
    }, maxSeconds * 1000);
  };

  const handleRetake = () => {
    stopRecording();
    recordedAudioRef.current = null;
    chunksRef.current = [];
    setIsRecorded(false);
    setAutoStopped(false);
    setElapsed(0);
    hasSpokenRef.current = false;
    setText("");
    baseTextRef.current = "";
    currentSpeechRef.current = "";
    meter.current.reset();
  };

  const handleToggleMic = () => {
    if (disabled || busy) return;
    if (isRecording) {
      stopRecording();
      return;
    }
    if (!consented) {
      setShowConsent(true);
      return;
    }
    void startRecordingSession();
  };

  const handleConsentAnswer = (agreed: boolean) => {
    setShowConsent(false);
    onConsent(agreed);
    if (agreed) {
      setActiveTab("VOICE");
      void startRecordingSession();
    } else {
      setActiveTab("TEXT");
      textareaRef.current?.focus();
    }
  };

  const handleSend = (e?: FormEvent) => {
    e?.preventDefault();
    if (busy || disabled) return;

    if (isRecording) {
      pendingSendRef.current = true;
      stopRecording();
      return;
    }

    void executeSend();
  };

  const handleKeyDown = (e: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const placeholder =
    turnType === "EXPLANATION" ? "Giảng lại khái niệm này bằng lời của bạn…" : "Trả lời câu hỏi của Whybi…";

  const isLimitReached = autoStopped || (elapsed >= maxSeconds && maxSeconds > 0 && !isRecording);
  const sendButtonLabel = hasSpokenRef.current ? "Gửi bản ghi" : (turnType === "EXPLANATION" ? "Gửi lời giảng" : "Gửi câu trả lời");

  return (
    <div className="space-y-2">
      {/* Tablist ẩn nhằm hỗ trợ accessibility và tương thích ngược */}
      <div role="tablist" aria-label="Cách giảng" className="sr-only">
        <button
          id="tab-VOICE"
          type="button"
          role="tab"
          aria-selected={activeTab === "VOICE"}
          onClick={() => setActiveTab("VOICE")}
        >
          Giọng nói
        </button>
        <button
          id="tab-TEXT"
          type="button"
          role="tab"
          aria-selected={activeTab === "TEXT"}
          onClick={() => {
            setActiveTab("TEXT");
            hasSpokenRef.current = false;
            textareaRef.current?.focus();
          }}
        >
          Văn bản
        </button>
      </div>

      {micError && (
        <div
          role="alert"
          className="space-y-2 rounded-lg border border-red-700/40 bg-st-fail/30 p-3 text-body-m text-red-900"
        >
          <p className="flex items-start gap-2">
            <TriangleAlert aria-hidden size={18} className="mt-0.5 shrink-0 text-red-700" />
            <span className="flex-1">{micError}</span>
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              onClick={() => {
                setMicError(null);
                setActiveTab("TEXT");
                textareaRef.current?.focus();
              }}
            >
              Chuyển sang gõ chữ
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setMicError(null);
                void startRecordingSession();
              }}
            >
              <RotateCcw aria-hidden size={14} /> Thử lại
            </Button>
          </div>
        </div>
      )}

      {isLimitReached && (
        <p role="status" className="flex items-center gap-1.5 text-body-s text-honey-deep">
          <TriangleAlert aria-hidden size={14} /> Đã đủ {Math.round(maxSeconds / 60)} phút – bản ghi tự dừng. Bấm Gửi hoặc Ghi lại.
        </p>
      )}

      {/* Khung chat hợp nhất theo mẫu UI-mau/thanh-chat.png */}
      <form
        onSubmit={handleSend}
        className="flex flex-col rounded-2xl border border-line-strong bg-ink-900 px-4 py-3 text-white shadow-card transition-all focus-within:border-teal/70 focus-within:ring-2 focus-within:ring-teal/30"
      >
        {/* Hàng trên: Thời gian - Mic - Thanh âm lượng ở chính giữa - Số ký tự */}
        <div className="flex items-center justify-between gap-3 border-b border-ink-700/50 pb-2.5">
          {/* Cụm bên trái: Thời gian ghi âm / giới hạn + Nút Mic */}
          <div className="flex items-center gap-2.5">
            <span
              className="text-body-s font-medium tabular-nums text-ink-300"
              aria-label={`Thời gian ghi âm: ${clockText(elapsed)} trên ${clockText(maxSeconds)}`}
            >
              {clockText(elapsed)} / {clockText(maxSeconds)}
            </span>

            <button
              type="button"
              onClick={handleToggleMic}
              disabled={disabled || busy}
              aria-label={isRecording ? "Dừng ghi âm" : "Bắt đầu ghi âm"}
              title={isRecording ? "Dừng ghi âm" : "Bắt đầu ghi âm"}
              className={`flex size-8 items-center justify-center rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-teal ${
                isRecording
                  ? "bg-red-600 text-white animate-pulse hover:bg-red-700"
                  : "bg-ink-700 text-ink-300 hover:bg-ink-600 hover:text-white"
              } disabled:opacity-50`}
            >
              {isRecording ? <Square aria-hidden size={14} fill="currentColor" /> : <Mic aria-hidden size={16} />}
            </button>

            {isRecording && (
              <span className="text-body-s font-semibold text-red-400 animate-pulse">
                Đang ghi
              </span>
            )}
            {isRecorded && !isRecording && (
              <button
                type="button"
                onClick={handleRetake}
                aria-label="Ghi lại"
                className="flex items-center gap-1 rounded-md bg-ink-800 px-2 py-1 text-body-s font-medium text-ink-300 hover:bg-ink-700 hover:text-white"
              >
                <RotateCcw aria-hidden size={13} /> Ghi lại
              </button>
            )}
          </div>

          {/* CHÍNH GIỮA: Thanh âm lượng giọng nói */}
          <div className="flex flex-1 items-center justify-center px-2">
            <Waveform
              stream={stream}
              active={isRecording}
              barsCount={20}
              className="flex h-5 items-center gap-[2px]"
              activeColor="bg-red-500"
              idleColor="bg-ink-700"
            />
          </div>

          {/* Cụm bên phải: Đếm số ký tự */}
          <div className="text-right">
            <span className="text-body-s font-medium tabular-nums text-ink-400">
              {text.length.toLocaleString("vi-VN")} / {MAX_TEXT.toLocaleString("vi-VN")}
            </span>
          </div>
        </div>

        {/* Khung nhập văn bản ở giữa: Tự co giãn và tự cuộn */}
        <div className="py-2.5">
          <label htmlFor="unified-turn-text" className="sr-only">
            {turnType === "EXPLANATION" ? "Lời giảng của bạn" : "Câu trả lời của bạn"}
          </label>
          <textarea
            ref={textareaRef}
            id="unified-turn-text"
            value={text}
            rows={2}
            maxLength={MAX_TEXT}
            aria-label={turnType === "EXPLANATION" ? "Lời giảng của bạn" : "Câu trả lời của bạn"}
            placeholder={placeholder}
            disabled={busy || disabled}
            onPaste={(e: ClipboardEvent<HTMLTextAreaElement>) =>
              meter.current.paste(e.clipboardData?.getData("text")?.length ?? 0)
            }
            onChange={(e) => {
              meter.current.change(text, e.target.value);
              setText(e.target.value);
              baseTextRef.current = e.target.value;
            }}
            onKeyDown={handleKeyDown}
            className="w-full resize-none border-none bg-transparent p-0 text-body-m text-white placeholder:text-ink-400 focus:outline-none focus:ring-0"
          />
        </div>

        {/* Hàng dưới: Nút gửi */}
        <div className="flex items-center justify-end pt-1">
          <button
            type="submit"
            disabled={(!text.trim() && !hasSpokenRef.current) || busy || disabled}
            aria-label={sendButtonLabel}
            title={sendButtonLabel}
            className="flex size-9 items-center justify-center rounded-lg bg-teal text-white shadow-float transition-all hover:brightness-110 active:scale-95 disabled:opacity-30 disabled:hover:brightness-100"
          >
            {busy ? (
              <LoaderCircle aria-hidden size={18} className="animate-spin" />
            ) : (
              <CornerDownLeft aria-hidden size={18} />
            )}
          </button>
        </div>
      </form>

      {/* Hộp thoại xin quyền ghi âm (BR-13) */}
      {showConsent && <ConsentDialog onAnswer={handleConsentAnswer} />}
    </div>
  );
}

/** Hộp đồng ý ghi âm (BR-13) – hiện trước khi trình duyệt xin quyền micro */
function ConsentDialog({ onAnswer }: { onAnswer: (ok: boolean) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const buttons = ref.current?.querySelectorAll<HTMLButtonElement>("button");
    buttons?.[buttons.length - 1]?.focus();
  }, []);

  function trap(e: ReactKeyboardEvent) {
    if (e.key === "Escape") return onAnswer(false);
    if (e.key !== "Tab") return;
    const buttons = Array.from(ref.current?.querySelectorAll<HTMLButtonElement>("button") ?? []);
    const i = buttons.indexOf(document.activeElement as HTMLButtonElement);
    e.preventDefault();
    buttons[(i + (e.shiftKey ? buttons.length - 1 : 1)) % buttons.length]?.focus();
  }

  return (
    <div className="fixed inset-0 z-30 flex items-end justify-center bg-ink-900/50 p-4 sm:items-center">
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby="consent-title"
        aria-describedby="consent-desc"
        onKeyDown={trap}
        className="w-full max-w-sm space-y-3 rounded-xl bg-surface p-5 shadow-dialog"
      >
        <h2 id="consent-title" className="flex items-center gap-2 text-h3 font-semibold text-ink-900">
          <ShieldCheck aria-hidden size={20} className="text-teal" /> Cho phép ghi âm lời giảng?
        </h2>
        <div id="consent-desc" className="space-y-2 text-body-m text-ink-700">
          <p>Whybi sẽ ghi âm giọng bạn để chuyển thành văn bản tức thời và chấm điểm lời giảng.</p>
          <p>Bạn luôn có thể chỉnh sửa chữ trực tiếp trong khung chat hoặc gõ chữ thay vì nói.</p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row-reverse">
          <Button variant="teal" className="flex-1" onClick={() => onAnswer(true)}>
            <Mic aria-hidden size={16} /> Đồng ý ghi âm
          </Button>
          <Button variant="secondary" className="flex-1" onClick={() => onAnswer(false)}>
            Không, tôi sẽ gõ chữ
          </Button>
        </div>
      </div>
    </div>
  );
}
