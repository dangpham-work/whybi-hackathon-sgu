/** Waveform – dạng sóng thời gian thực bằng Web Audio AnalyserNode (FR-TB-05). Thẻ: GD-07 (Thắng). */
export function Waveform({ stream }: { stream?: MediaStream }) {
  // TODO(GD-07): AnalyserNode → vẽ cột như Figma SV-04 (đỏ khi đang ghi)
  return <div className="h-8 text-ink-500">{stream ? "…" : "Waveform – thẻ GD-07"}</div>;
}
