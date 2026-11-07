import { Play, RotateCcw, Check, TriangleAlert } from "lucide-react";
import { useState } from "react";
import type { Schema } from "../lib/api";
import { editRatio, markUncertain, MAX_EDIT_RATIO, STT_THRESHOLD } from "../lib/transcript";
import { Button } from "./Button";

/**
 * SV-05 Xác nhận bản chép lời (Figma 25:1280, FR-TB-06/07, GD-08): gạch chân từ không chắc, cho sửa nhỏ.
 * Sửa quá nhiều thì không cho gửi – SV phải ghi âm lại (sửa lỗi nhận dạng, không viết lại lời giảng).
 */
export function TranscriptConfirm({
  transcript,
  audioUrl,
  busy,
  onConfirm,
  onRetry,
  onCancel,
}: {
  transcript: Schema<"Transcript">;
  audioUrl?: string;
  busy?: boolean;
  onConfirm: (text: string, edited: boolean) => void;
  onRetry: () => void;
  onCancel: () => void;
}) {
  const [text, setText] = useState(transcript.text);
  const [player, setPlayer] = useState<HTMLAudioElement | null>(null);
  const ratio = editRatio(transcript.text, text);
  const tooMuch = ratio > MAX_EDIT_RATIO;
  const empty = !text.trim();
  const uncertain = transcript.lowConfidenceWords;

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="sv05-title" className="fixed inset-0 z-40 flex items-end bg-ink-900/50">
      <div className="max-h-[90vh] w-full space-y-3 overflow-y-auto rounded-t-2xl bg-surface p-4 shadow-dialog">
        <h2 id="sv05-title" className="flex items-center gap-2 text-h2 font-bold">
          <TriangleAlert aria-hidden size={20} className="text-honey-deep" /> Kiểm tra bản chép lời
        </h2>
        <p className="text-body-s text-ink-500">
          Whybi chưa chắc chắn ở một vài từ (gạch chân). Bạn chỉ nên sửa lỗi nhận dạng, không viết lại nội dung – chỉnh sửa lớn sẽ không được ghi nhận.
        </p>

        {uncertain.length > 0 && (
          <p aria-label="Văn bản gốc, từ không chắc được gạch chân" className="rounded-lg bg-app p-3 text-body-m">
            {markUncertain(transcript.text, uncertain).map((p, i) =>
              p.uncertain ? (
                <u key={i} className="decoration-honey-deep decoration-wavy underline-offset-4" title="Độ tin cậy thấp">
                  {p.text}
                </u>
              ) : (
                <span key={i}>{p.text}</span>
              ),
            )}
          </p>
        )}

        <label className="block space-y-1">
          <span className="text-body-s font-semibold">Bản chép lời (có thể sửa)</span>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={5}
            className="w-full rounded-lg border border-line-strong p-3 text-body-m focus-visible:outline-2 focus-visible:outline-teal"
          />
        </label>

        <p className="flex items-center justify-between text-body-s text-ink-500">
          <span>
            Độ tin cậy STT <strong className="text-h3 text-honey-deep">{transcript.confidence.toFixed(2).replace(".", ",")}</strong> · ngưỡng{" "}
            {STT_THRESHOLD.toFixed(2).replace(".", ",")}
          </span>
          <span>Đã sửa {Math.round(ratio * 100)}%</span>
        </p>
        {tooMuch && (
          <p role="alert" className="flex items-start gap-2 rounded-md border border-red-700/40 bg-st-fail/40 px-3 py-2 text-body-s text-red-900">
            <TriangleAlert aria-hidden size={14} className="mt-0.5 shrink-0" /> Bạn đã sửa quá nhiều so với bản ghi âm. Hãy ghi âm lại thay vì viết lại nội dung.
          </p>
        )}

        {audioUrl && <audio ref={setPlayer} src={audioUrl} className="hidden" />}
        <div className="grid grid-cols-2 gap-2">
          <Button variant="secondary" onClick={() => void player?.play()} disabled={!audioUrl}>
            <Play aria-hidden size={16} /> Nghe lại
          </Button>
          <Button variant="secondary" onClick={onRetry}>
            <RotateCcw aria-hidden size={16} /> Ghi âm lại
          </Button>
          <Button variant="secondary" onClick={onCancel}>
            Hủy
          </Button>
          <Button disabled={busy || tooMuch || empty} onClick={() => onConfirm(text.trim(), text.trim() !== transcript.text.trim())}>
            <Check aria-hidden size={16} /> Xác nhận và gửi
          </Button>
        </div>
      </div>
    </div>
  );
}
