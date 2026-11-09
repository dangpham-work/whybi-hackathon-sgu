import {
  CircleCheck,
  CircleX,
  FileText,
  FileUp,
  Hourglass,
  LoaderCircle,
  Pencil,
  Square,
  UploadCloud,
  X,
} from "lucide-react";
import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import { DevelopingBox, ErrorBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { TocPanel, type BuildOptions } from "../../components/TocPanel";
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
  AWAITING_SELECTION: "Đang chờ thầy/cô chọn phần cần dựng cây (xem cảnh báo bên dưới)",
  CONCEPTS: "Trích khái niệm",
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

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

/** GV-03 Tải giáo trình & tiến độ (Figma 14:1468, FR-SK-02/03, GD-05). Tiến độ nghe kênh `job:{jobId}`. */
export default function LecturerSyllabus() {
  const { classId = "" } = useParams();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File>();
  const [isDragging, setIsDragging] = useState(false);
  const [problem, setProblem] = useState<string>();
  const [failure, setFailure] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [jobId, setJobId] = useState<string>();
  const [documentId, setDocumentId] = useState<string>();
  const [progress, setProgress] = useState<Progress>();
  const [treeReady, setTreeReady] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [toc, setToc] = useState<Schema<"TocReport">>();
  const [building, setBuilding] = useState(false);
  const [buildFailure, setBuildFailure] = useState<unknown>();

  /** Báo cáo mục lục & cảnh báo cỡ giáo trình do worker lưu; lỗi tải thì bỏ qua, luồng dựng cây không phụ thuộc vào nó. */
  async function loadToc(docId: string) {
    try {
      setToc(await apiCall("get", "/classes/{class_id}/syllabi/{document_id}/toc", { path: { class_id: classId, document_id: docId } }));
    } catch {
      setToc(undefined);
    }
  }

  /** Tải lại trang: báo cáo vẫn lưu ở backend, nên nếu giáo trình mới nhất còn đang chờ chọn thì khôi phục hộp cảnh báo. */
  useEffect(() => {
    const ctrl = new AbortController();
    apiCall("get", "/classes/{class_id}/syllabi/latest/toc", { path: { class_id: classId }, signal: ctrl.signal })
      .then((t) => {
        if (ctrl.signal.aborted || !t.gated) return;
        setToc(t);
        setJobId((j) => j ?? t.documentId);
        setDocumentId((d) => d ?? t.documentId);
        setProgress((p) => p ?? { percent: 100, step: "AWAITING_SELECTION" });
      })
      .catch(() => {}); // chưa có giáo trình / báo cáo ⇒ trang trống như thường
    return () => ctrl.abort();
  }, [classId]);

  useChannel(jobId ? `job:${jobId}` : null, (e) => {
    if (e.event === "job.progress") setProgress(e.payload as Progress);
    // `DONE` đầu tiên chỉ là bóc chữ xong; cây dựng xong khi worker phát `tree.generated`
    if (e.event === "tree.generated") setTreeReady(true);
    if (e.event === "syllabus.toc_ready") void loadToc((e.payload as { documentId: string }).documentId);
  });

  async function build({ ranges, detail, lazyRubric }: BuildOptions) {
    if (!toc || building) return;
    setBuilding(true);
    setBuildFailure(undefined);
    try {
      await apiCall("post", "/classes/{class_id}/syllabi/{document_id}/build-tree", {
        path: { class_id: classId, document_id: toc.documentId },
        body: { ranges: ranges.map(([from, to]) => [from, to]), detail, lazyRubric },
      });
      setToc({ ...toc, gated: false });
      setTreeReady(false);
      setProgress({ percent: 0, step: "CONCEPTS" });
    } catch (err) {
      setBuildFailure(err instanceof ApiError ? new Error(errorText(err)) : err);
    } finally {
      setBuilding(false);
    }
  }

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
    setToc(undefined);
    setBuildFailure(undefined);
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

  const PHASES = [
    { id: 1, name: "Bóc tách văn bản", steps: ["DOWNLOADING", "EXTRACTING", "OCR", "SAVING"] },
    { id: 2, name: "Trích xuất khái niệm", steps: ["AWAITING_SELECTION", "CONCEPTS", "DEDUPE"] },
    { id: 3, name: "Dựng cây kỹ năng", steps: ["PREREQUISITES", "TREE", "INDEXING"] },
    { id: 4, name: "Sinh rubric đánh giá", steps: ["RUBRICS", "DONE"] },
  ];

  const currentPhaseIndex = PHASES.findIndex((p) => p.steps.includes(progress?.step ?? ""));

  function handleDragOver(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    if (!running) setIsDragging(true);
  }

  function handleDragLeave(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    setIsDragging(false);
  }

  function handleDrop(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    setIsDragging(false);
    if (running) return;
    const f = e.dataTransfer.files?.[0];
    if (f) pick(f);
  }

  return (
    <div className="space-y-6 p-4 lg:p-7">
      <header>
        <h1 className="text-h1 font-bold">Tải giáo trình & sinh cây kỹ năng</h1>
        <p className="text-body-m text-ink-500">Whybi AI đọc giáo trình, trích khái niệm và suy luận quan hệ tiên quyết.</p>
      </header>

      <form onSubmit={upload} className="space-y-4 rounded-xl border border-line-soft bg-surface p-5 shadow-card">
        <div className="flex items-center justify-between">
          <h2 className="text-h3 font-semibold">Tệp giáo trình / đề cương</h2>
          <span className="text-body-s text-ink-400">PDF, DOCX · Tối đa 20 MB</span>
        </div>

        {!file ? (
          <label
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`group relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center transition-all cursor-pointer ${
              isDragging
                ? "border-teal bg-teal-soft/30 scale-[1.01]"
                : "border-line-strong hover:border-honey/80 hover:bg-honey-soft/20 bg-surface/50"
            }`}
          >
            <input
              ref={input}
              type="file"
              aria-label="Chọn tệp giáo trình"
              accept=".pdf,.docx"
              disabled={running}
              onChange={(e) => pick(e.target.files?.[0])}
              className="sr-only"
            />
            <div className="flex size-14 items-center justify-center rounded-full bg-honey-soft text-honey-deep mb-3 shadow-inner group-hover:scale-105 transition-transform">
              <UploadCloud size={28} />
            </div>
            <p className="text-body-m font-semibold text-ink-900">
              Kéo & thả tệp đề cương / giáo trình vào đây, hoặc <span className="text-teal underline underline-offset-2">duyệt từ máy tính</span>
            </p>
            <p className="mt-1.5 text-body-s text-ink-500">
              Bản quét scan được tự động nhận dạng bằng bộ OCR tiếng Việt chuyên sâu.
            </p>
          </label>
        ) : (
          <div className="rounded-xl border border-line-soft bg-app/60 p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3 min-w-0">
                <div className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-teal-soft text-teal">
                  <FileText size={24} />
                </div>
                <div className="min-w-0">
                  <p className="truncate text-body-m font-bold text-ink-900" title={file.name}>
                    {file.name}
                  </p>
                  <p className="text-body-s text-ink-500">{formatBytes(file.size)}</p>
                </div>
              </div>
              {!running && (
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => input.current?.click()}
                    className="rounded-md border border-line-strong bg-surface px-3 py-1.5 text-body-s font-semibold hover:bg-app text-ink-700 shadow-sm transition"
                  >
                    Đổi tệp
                  </button>
                  <button
                    type="button"
                    onClick={() => pick(undefined)}
                    aria-label="Bỏ chọn tệp"
                    className="rounded-md border border-line-strong p-1.5 text-ink-500 hover:text-red-700 hover:bg-red-50 transition"
                  >
                    <X size={16} />
                  </button>
                </div>
              )}
            </div>
            <input
              ref={input}
              type="file"
              aria-label="Chọn tệp giáo trình"
              accept=".pdf,.docx"
              disabled={running}
              onChange={(e) => pick(e.target.files?.[0])}
              className="sr-only"
            />
          </div>
        )}

        {problem && <ErrorBox text={problem} />}
        {failure !== undefined &&
          (failure instanceof ApiError && failure.notImplemented ? (
            <DevelopingBox text={failure.message} />
          ) : (
            <ErrorBox text={(failure instanceof ApiError && UPLOAD_ERRORS[failure.code]) || errorText(failure)} />
          ))}

        <div className="flex items-center justify-between pt-1">
          <p className="text-body-s text-ink-500">Giới hạn 20 MB, định dạng PDF hoặc DOCX. Bản quét được nhận dạng bằng OCR tiếng Việt.</p>
          <Button type="submit" disabled={!file || !!problem || busy || running}>
            <FileUp aria-hidden size={18} /> {busy ? "Đang tải lên…" : "Tải lên và phân tích"}
          </Button>
        </div>
      </form>

      {progress && (
        <section aria-label="Tiến độ phân tích" className="space-y-4 rounded-xl border border-line-soft bg-surface p-5 shadow-card">
          <div className="flex items-center justify-between border-b border-line-soft pb-3">
            <div>
              <h2 className="text-h3 font-semibold">Tiến độ phân tích Whybi AI</h2>
              <p className="text-body-s text-ink-500">Hệ thống đang xử lý tự động theo mô hình sư phạm</p>
            </div>
            <div className="text-right">
              <span className="text-h2 font-black text-honey-deep">{progress.percent}%</span>
            </div>
          </div>

          <div
            role="progressbar"
            aria-label="Tiến độ phân tích giáo trình"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progress.percent}
            className="h-2.5 overflow-hidden rounded-full bg-app"
          >
            <div
              className={`h-full transition-all duration-300 ${
                failed ? "bg-red-600" : "bg-gradient-to-r from-honey to-teal"
              }`}
              style={{ width: `${progress.percent}%` }}
            />
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 pt-1">
            {PHASES.map((phase, idx) => {
              const isPast = done || (currentPhaseIndex >= 0 && idx < currentPhaseIndex);
              const isCurrent = !done && idx === currentPhaseIndex;
              return (
                <div
                  key={phase.id}
                  className={`rounded-lg border p-2.5 text-center transition-all ${
                    isCurrent
                      ? "border-honey bg-honey-soft/40 shadow-sm"
                      : isPast
                      ? "border-teal/40 bg-teal-soft/20 text-teal"
                      : "border-line-soft bg-app/50 text-ink-400"
                  }`}
                >
                  <p className="text-caption font-bold">BƯỚC {phase.id}</p>
                  <p className="truncate text-body-s font-semibold text-ink-900" title={phase.name}>
                    {phase.name}
                  </p>
                </div>
              );
            })}
          </div>

          <p role="status" className="flex items-center gap-2 text-body-m font-medium pt-1">
            {failed || cancelled ? (
              <CircleX aria-hidden size={18} className="text-red-700" />
            ) : done ? (
              <CircleCheck aria-hidden size={18} className="text-teal" />
            ) : waiting ? (
              <Hourglass aria-hidden size={18} className="text-honey-deep" />
            ) : (
              <LoaderCircle aria-hidden size={18} className="animate-spin text-teal" />
            )}
            {STEP_LABEL[progress.step] ?? progress.step}
          </p>

          <div className="flex flex-wrap items-center gap-3 pt-2">
            {running && documentId && (
              <Button type="button" variant="secondary" onClick={cancel} disabled={cancelling}>
                <Square aria-hidden size={16} /> {cancelling ? "Đang hủy…" : "Hủy"}
              </Button>
            )}
            {done && (
              <Link
                to={`/gv/classes/${classId}/tree`}
                className="inline-flex items-center gap-2 rounded-lg bg-teal px-5 py-2.5 font-semibold text-white shadow-md hover:brightness-110 transition-all"
              >
                <Pencil aria-hidden size={18} /> Mở trình sửa cây
              </Link>
            )}
          </div>
          {failed && <ErrorBox text="Không xử lý được giáo trình này. Kiểm tra tệp rồi tải lại." />}
        </section>
      )}

      {toc && toc.level !== "OK" && <TocPanel key={toc.documentId} report={toc} busy={building} error={buildFailure} onBuild={build} />}
    </div>
  );
}
