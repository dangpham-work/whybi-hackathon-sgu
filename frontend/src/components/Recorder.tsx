/**
 * Recorder – ghi âm MediaRecorder (webm/opus), ≤ 3 phút lời giảng / 90 giây câu trả lời,
 * hỏi đồng ý trước lần đầu (BR-13), luôn có nút chuyển sang gõ văn bản. Thẻ: GD-07 (Thắng).
 */
export function Recorder({ maxSeconds = 180 }: { maxSeconds?: number }) {
  // TODO(GD-07): getUserMedia + MediaRecorder; gửi multipart tới POST /sessions/{id}/audio
  return <div className="text-ink-500">Recorder ≤ {maxSeconds}s – thẻ GD-07</div>;
}
