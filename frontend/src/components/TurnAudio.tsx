import { LoaderCircle, Volume2 } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError } from "../lib/api";
import { fetchAudioUrl } from "../lib/audio";

/** Nút "Nghe ghi âm" một lượt (FR-HM-07). Chỉ tải khi GV bấm; hết hạn lưu / không đồng ý lưu thì báo rõ. */
export function TurnAudio({ audioUrl }: { audioUrl: string }) {
  const [state, setState] = useState<{ kind: "idle" } | { kind: "loading" } | { kind: "ready"; url: string } | { kind: "gone" } | { kind: "error" }>({ kind: "idle" });
  useEffect(() => () => void (state.kind === "ready" && URL.revokeObjectURL(state.url)), [state]);

  async function load() {
    setState({ kind: "loading" });
    try {
      setState({ kind: "ready", url: await fetchAudioUrl(audioUrl) });
    } catch (e) {
      setState(e instanceof ApiError && e.status === 404 ? { kind: "gone" } : { kind: "error" });
    }
  }
  if (state.kind === "ready") return <audio controls autoPlay src={state.url} aria-label="Ghi âm lượt này" className="mt-1 h-9 w-full" />;
  if (state.kind === "gone") return <p className="text-body-s text-ink-500">Ghi âm không còn (không được lưu hoặc đã quá hạn lưu).</p>;
  return (
    <button type="button" onClick={load} disabled={state.kind === "loading"} className="mt-1 inline-flex items-center gap-1 text-body-s font-semibold text-teal hover:underline">
      {state.kind === "loading" ? <LoaderCircle aria-hidden size={14} className="animate-spin" /> : <Volume2 aria-hidden size={14} />}
      {state.kind === "error" ? "Không tải được – thử lại" : "Nghe ghi âm"}
    </button>
  );
}
