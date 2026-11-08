import { CircleCheck, CircleX, FileUp, LoaderCircle, Pencil, Square } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import { DevelopingBox, ErrorBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { ApiError, apiCall, errorText, type Schema } from "../../lib/api";
import { useChannel } from "../../lib/ws";

const MAX_BYTES = 20 * 1024 * 1024;
const EXT = /\.(pdf|docx)$/i;
/** Các bước `job.progress.step` do worker documents phát (docs/status/dang.md, C1-09). */
const STEP_LABEL: Record<string, string> = {
  DOWNLOADING: "Nhận tệp giáo trình",
  EXTRACTING: "Trích văn bản theo trang",
  OCR: "Nhận dạng chữ trang quét (OCR)",
  SAVING: "Lưu văn bản đã tách",
  AWAITING_SELECTION: "Giáo trình lớn – chờ bạn chọn chương trước khi dựng cây",
  CONCEPTS: "Trích khái niệm từng chương",
  DEDUPE: "Gộp khái niệm trùng",
  PREREQUISITES: "Suy luận quan hệ tiên quyết",
  TREE: "Dựng cây kỹ năng",
  INDEXING: "Lập chỉ mục giáo trình",
  RUBRICS: "Sinh rubric cho từng nút",
  DONE: "Hoàn tất",
  FAILED: "Xử lý lỗi",
  CANCELLED: "Đã hủy",
};
interface Progress {
  percent: number;
  step: string;
}

const UPLOAD_ERRORS: Record<string, string> = {
  INVALID_FILE: "Tệp không hợp lệ – chỉ nhận PDF hoặc DOCX thật.",
  FILE_TOO_LARGE: "Tệp vượt quá 20 MB. Hãy tách nhỏ hoặc nén lại.",
};

/** Kiểm tra phía trình duyệt trước khi gửi (máy chủ vẫn kiểm lại, TC01). */
export function checkFile(f: File): string | null {
  if (!EXT.test(f.name)) return UPLOAD_ERRORS.INVALID_FILE;
  if (f.size > MAX_BYTES) return UPLOAD_ERRORS.FILE_TOO_LARGE;
  return null;
}

/** GV-03 Tải giáo trình & tiến độ (Figma 14:1468, FR-SK-02/03, GD-05). Tiến độ nghe kênh `job:{jobId}`. */
export default function LecturerSyllabus() {
  const { classId = "" } = useParams();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File>();
  const [problem, setProblem] = useState<string>();
  const [failure, setFailure] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [jobId, setJobId] = useState<string>();
  const [documentId, setDocumentId] = useState<string>();
  const [progress, setProgress] = useState<Progress>();
  const [treeReady, setTreeReady] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  useChannel(jobId ? `job:${jobId}` : null, (e) => {
    if (e.event === "job.progress") setProgress(e.payload as Progress);
    // `DONE` đầu tiên chỉ là bóc chữ xong; cây dựng xong khi worker phát `tree.generated`
    if (e.event === "tree.generated") setTreeReady(true);
  });

  function pick(f: File | undefined) {
    setFile(f);
    setProblem(f ? (checkFile(f) ?? undefined) : undefined);
    setFailure(undefined);
  }

  async function upload(e: FormEvent) {
    e.preventDefault();
    if (!file || problem || busy) return;
    setBusy(true);
    setFailure(undefined);
    setTreeReady(false);
    setProgress({ percent: 0, step: "DOWNLOADING" });
    try {
      const form = new FormData();
      form.append("file", file);
      // OpenAPI chưa khai báo thân 202 nên kiểu trả về là void – ép về JobAccepted
      const job = (await apiCall("post", "/classes/{class_id}/syllabi", { path: { class_id: classId }, body: form as never })) as unknown as Schema<"JobAccepted">;
      setJobId(job.jobId);
      setDocumentId(job.documentId);
    } catch (err) {
      setFailure(err);
      setProgress(undefined);
    } finally {
      setBusy(false);
    }
  }

  const failed = progress?.step === "FAILED";
  const cancelled = progress?.step === "CANCELLED";
  const waiting = progress?.step === "AWAITING_SELECTION";
  const done = treeReady;
  const running = !!jobId && !done && !failed && !cancelled && !waiting;

  async function cancel() {
    if (!documentId || cancelling) return;
    setCancelling(true);
    try {
      await apiCall("post", "/classes/{class_id}/syllabi/{document_id}/cancel", {
        path: { class_id: classId, document_id: documentId },
      });
    } catch (err) {
      setFailure(err);
    } finally {
      setCancelling(false);
    }
  }

  return (
    <div className="space-y-6 p-4 lg:p-7">
      <header>
        <h1 className="text-h1 font-bold">Tải giáo trình & sinh cây kỹ năng</h1>
        <p className="text-body-m text-ink-500">Whybi AI đọc giáo trình, trích khái niệm và suy luận quan hệ tiên quyết.</p>
      </header>

      <form onSubmit={upload} className="space-y-3 rounded-lg border border-line-soft bg-surface p-5">
        <h2 className="text-h3 font-semibold">Tệp giáo trình</h2>
        <input
          ref={input}
          type="file"
          aria-label="Chọn tệp giáo trình"
          accept=".pdf,.docx"
          disabled={running}
          onChange={(e) => pick(e.target.files?.[0])}
          className="block w-full text-body-m"
        />
        <p className="text-body-s text-ink-500">Giới hạn 20 MB, định dạng PDF hoặc DOCX. Bản quét được nhận dạng bằng OCR tiếng Việt.</p>
        {problem && <ErrorBox text={problem} />}
        {failure !== undefined &&
          (failure instanceof ApiError && failure.notImplemented ? (
            <DevelopingBox text={failure.message} />
          ) : (
            <ErrorBox text={(failure instanceof ApiError && UPLOAD_ERRORS[failure.code]) || errorText(failure)} />
          ))}
        <Button type="submit" disabled={!file || !!problem || busy || running}>
          <FileUp aria-hidden size={18} /> {busy ? "Đang tải lên…" : "Tải lên và phân tích"}
        </Button>
      </form>

      {progress && (
        <section aria-label="Tiến độ phân tích" className="space-y-3 rounded-lg border border-line-soft bg-surface p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-h3 font-semibold">Tiến độ phân tích</h2>
            <span className="text-h3 font-bold text-honey-deep">{progress.percent}%</span>
          </div>
          <div
            role="progressbar"
            aria-label="Tiến độ phân tích giáo trình"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progress.percent}
            className="h-2 overflow-hidden rounded-full bg-app"
          >
            <div className={`h-full ${failed ? "bg-red-600" : "bg-honey"}`} style={{ width: `${progress.percent}%` }} />
          </div>
          <p role="status" className="flex items-center gap-2 text-body-m">
            {failed || cancelled ? <CircleX aria-hidden size={18} className="text-red-700" /> : done ? <CircleCheck aria-hidden size={18} className="text-teal" /> : <LoaderCircle aria-hidden size={18} className="animate-spin text-teal" />}
            {STEP_LABEL[progress.step] ?? progress.step}
          </p>
          {running && documentId && (
            <Button type="button" variant="secondary" onClick={cancel} disabled={cancelling}>
              <Square aria-hidden size={16} /> {cancelling ? "Đang hủy…" : "Hủy"}
            </Button>
          )}
          {failed && <ErrorBox text="Không xử lý được giáo trình này. Kiểm tra tệp rồi tải lại." />}
          {done && (
            <Link to={`/gv/classes/${classId}/tree`} className="inline-flex items-center gap-2 rounded-md bg-teal px-4 py-2 font-semibold text-white">
              <Pencil aria-hidden size={16} /> Mở trình sửa cây
            </Link>
          )}
        </section>
      )}
    </div>
  );
}
