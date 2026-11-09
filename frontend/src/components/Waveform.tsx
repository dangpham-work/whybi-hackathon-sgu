import { useEffect, useRef } from "react";

const BARS = 28;
const IDLE = [0.25, 0.4, 0.3, 0.55, 0.35, 0.7, 0.45, 0.3];

type AudioCtor = typeof AudioContext;
const audioContextCtor = (): AudioCtor | undefined =>
  (globalThis as { AudioContext?: AudioCtor; webkitAudioContext?: AudioCtor }).AudioContext ??
  (globalThis as { webkitAudioContext?: AudioCtor }).webkitAudioContext;

/**
 * Waveform – dạng sóng thời gian thực bằng Web Audio AnalyserNode (FR-TB-05, Figma SV-04). Thẻ: GD-07.
 * Cột đỏ khi đang ghi, xám khi dừng. Trình duyệt không có Web Audio (hoặc chưa có stream) → cột tĩnh.
 * Cập nhật chiều cao cột thẳng vào DOM trong requestAnimationFrame, không setState mỗi khung hình.
 */
export function Waveform({
  stream,
  active = false,
  barsCount = BARS,
  className = "flex h-8 flex-1 items-center gap-[3px]",
  activeColor = "bg-red-600",
  idleColor = "bg-line-strong",
}: {
  stream?: MediaStream;
  active?: boolean;
  barsCount?: number;
  className?: string;
  activeColor?: string;
  idleColor?: string;
}) {
  const bars = useRef<(HTMLSpanElement | null)[]>([]);

  useEffect(() => {
    const Ctor = audioContextCtor();
    if (!stream || !active || !Ctor) return;
    let ctx: AudioContext | undefined;
    let analyser: AnalyserNode;
    try {
      ctx = new Ctor();
      if (ctx.state === "suspended") void ctx.resume();
      analyser = ctx.createAnalyser();
      analyser.fftSize = 64;
      ctx.createMediaStreamSource(stream).connect(analyser);
    } catch {
      void ctx?.close().catch(() => undefined);
      return; // không dựng được đồ thị âm thanh → giữ cột tĩnh, việc ghi âm vẫn chạy
    }
    const data = new Uint8Array(analyser.frequencyBinCount);
    let frame = 0;
    const draw = () => {
      analyser.getByteFrequencyData(data);
      bars.current.forEach((el, i) => {
        if (!el) return;
        const v = data[Math.floor((i / barsCount) * data.length)] / 255;
        el.style.height = `${Math.max(12, Math.round(v * 100))}%`;
      });
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(frame);
      void ctx?.close().catch(() => undefined);
    };
  }, [stream, active, barsCount]);

  return (
    <div role="img" aria-label={active ? "Dạng sóng âm thanh đang ghi" : "Dạng sóng âm thanh"} className={className}>
      {Array.from({ length: barsCount }, (_, i) => (
        <span
          key={i}
          ref={(el) => {
            bars.current[i] = el;
          }}
          className={`w-[3px] rounded-full transition-[height] duration-75 ${active ? activeColor : idleColor}`}
          style={{ height: `${IDLE[i % IDLE.length] * 100}%` }}
        />
      ))}
    </div>
  );
}
