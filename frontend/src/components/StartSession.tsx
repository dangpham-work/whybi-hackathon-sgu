/**
 * Bắt đầu phiên giảng lại từ SV-02 / SV-03 (GD-06): POST /sessions {nodeId} → SV-04 /sv/sessions/:sessionId.
 * Hợp đồng: SessionStart / SessionCreated (backend/app/models/schemas/session.py, C1-07 – còn 501);
 * mã lỗi 409 NODE_LOCKED | RETRY_COOLDOWN | NODE_ALREADY_MASTERED | SESSION_IN_PROGRESS {sessionId} theo C2-10 (schemas/mastery.py).
 * Giả định: POST /sessions trả nguyên mã lỗi của MasteryService.start_session; câu mở đầu (`opening`) chuyển cho SV-04 qua state.
 */
import { PlayCircle } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { ApiError, apiCall, errorText } from "../lib/api";
import { DevelopingBox, ErrorBox } from "./AsyncView";

export function useStartSession() {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>();

  async function start(nodeId: string) {
    if (busy) return;
    setBusy(true);
    setFailure(undefined);
    try {
      // Chọn giọng nói / gõ chữ ở SV-04; ở đây gửi mặc định của backend (TEXT, không TTS).
      const s = await apiCall("post", "/sessions", { body: { nodeId, inputMode: "TEXT", ttsEnabled: false } });
      navigate(`/sv/sessions/${s.sessionId}`, { state: { opening: s.opening } });
    } catch (err) {
      setFailure(err);
      setBusy(false);
    }
  }

  return { start, busy, failure };
}

/** Hiển thị lỗi khi bắt đầu phiên: 501 → đang phát triển; đang có phiên → link tiếp tục; còn lại → câu trong FRIENDLY. */
export function StartSessionError({ failure }: { failure: unknown }) {
  if (failure === undefined) return null;
  if (failure instanceof ApiError && failure.notImplemented) return <DevelopingBox text={failure.message} />;
  const running = failure instanceof ApiError && failure.code === "SESSION_IN_PROGRESS" ? failure.details.sessionId : undefined;
  return (
    <div className="space-y-2">
      <ErrorBox text={errorText(failure)} />
      {typeof running === "string" && (
        <Link
          to={`/sv/sessions/${running}`}
          className="inline-flex items-center gap-2 rounded-md border border-line-strong bg-surface px-4 py-2 text-body-m font-semibold text-ink-900 hover:bg-app"
        >
          <PlayCircle aria-hidden size={16} /> Tiếp tục phiên đang giảng
        </Link>
      )}
    </div>
  );
}
