import { Check, ListChecks, Sparkles, TriangleAlert, X } from "lucide-react";
import { useMemo, useState } from "react";
import { type Schema } from "../lib/api";
import {
  DETAILS,
  chunksFor,
  defaultSelected,
  estimateScope,
  hasPageMap,
  pagesIn,
  parsePageRanges,
  rangesFromChapters,
  type Detail,
  type Range,
} from "../lib/syllabus-scope";
import { Button } from "./Button";
import { ErrorBox } from "./AsyncView";

const SOURCE: Record<string, string> = {
  bookmark: "Mục lục lấy từ bookmark của tệp.",
  toc_pages: "Mục lục lấy từ các trang mục lục in trong sách.",
  none: "Không tìm thấy mục lục trong tệp.",
};

export interface BuildOptions {
  ranges: Range[];
  detail: Detail;
  lazyRubric: boolean;
}

/**
 * Cảnh báo cỡ giáo trình + chọn phần cần dựng cây (GV-03). Dựng cây tốn token theo số nút nên giáo trình lớn
 * được dừng lại đây: AI viết lời khuyên từ mục lục đã trích, thầy/cô tick chương (hoặc gõ khoảng trang) rồi mới dựng.
 * `report.gated = false` (cổng tắt hoặc đã bấm dựng) ⇒ chỉ hiện lời khuyên, không có nút.
 */
export function TocPanel({
  report,
  busy,
  error,
  onBuild,
}: {
  report: Schema<"TocReport">;
  busy: boolean;
  error?: unknown;
  onBuild: (opts: BuildOptions) => void;
}) {
  const { chapters, advice } = report;
  const byChapter = hasPageMap(chapters);
  const [selected, setSelected] = useState<Set<number>>(() => defaultSelected(report));
  const [text, setText] = useState("");
  const [detail, setDetail] = useState<Detail>("STANDARD");
  const [lazyRubric, setLazyRubric] = useState(true); // panel chỉ hiện với giáo trình lớn ⇒ mặc định hoãn rubric để tiết kiệm

  const skipReason = useMemo(() => new Map(advice.skip.map((s) => [s.index, s.reason])), [advice.skip]);
  const keep = useMemo(() => new Set(advice.keep), [advice.keep]);

  const typed = parsePageRanges(text, report.totalPages);
  const ranges = byChapter ? rangesFromChapters(chapters, selected) : typed.ranges;
  const chosenPages = pagesIn(ranges);
  const invalid = !byChapter && typed.error;
  const canBuild = report.gated && !busy && ranges.length > 0 && !invalid;
  const tooLarge = report.level === "TOO_LARGE";
  const chunks = chunksFor(report, selected, ranges);
  const est = estimateScope(report, chunks, detail, lazyRubric);
  const locked = !report.gated || busy;

  function toggle(index: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  return (
    <section aria-label="Cảnh báo cỡ giáo trình" className="space-y-4 rounded-lg border border-honey bg-honey-soft p-5">
      <header className="flex items-start gap-3">
        <TriangleAlert aria-hidden size={22} className="mt-0.5 shrink-0 text-honey-deep" />
        <div className="space-y-1">
          <h2 className="text-h3 font-semibold">
            {tooLarge ? "Giáo trình rất lớn – nên khoanh vùng trước khi dựng cây" : "Giáo trình khá lớn – nên khoanh vùng trước khi dựng cây"}
          </h2>
          <p className="text-body-m">{advice.message}</p>
          <p className="flex items-center gap-1 text-body-s text-ink-500">
            <Sparkles aria-hidden size={14} />
            {report.aiWritten ? "Lời khuyên do AI viết từ mục lục đã trích." : "Lời khuyên tự động từ số liệu giáo trình."}
          </p>
        </div>
      </header>

      <dl className="grid grid-cols-3 gap-3 text-center">
        {[
          [report.totalPages, "trang"],
          [`~${report.estNodes}`, "nút cây dự kiến"],
          [`~${report.estCalls}`, "lượt gọi AI dự kiến"],
        ].map(([value, label]) => (
          <div key={label} className="rounded-md bg-surface p-3">
            <dd className="text-h3 font-bold">{value}</dd>
            <dt className="text-body-s text-ink-500">{label}</dt>
          </div>
        ))}
      </dl>
      <p className="text-body-s text-ink-500">
        {SOURCE[report.source] ?? SOURCE.none} Danh sách chương do hệ thống tự trích nên có thể thiếu hoặc sai.
        {advice.suggestSplit && " Nên tách giáo trình thành nhiều tệp hoặc dựng cây theo từng đợt."}
      </p>

      {byChapter ? (
        <fieldset className="space-y-2" disabled={!report.gated || busy}>
          <legend className="mb-1 flex items-center gap-2 font-semibold">
            <ListChecks aria-hidden size={18} /> Chọn chương cần dựng cây
          </legend>
          <ul className="max-h-80 space-y-1 overflow-y-auto rounded-md bg-surface p-2">
            {chapters.map((c) => (
              <li key={c.index}>
                <label className="flex cursor-pointer flex-wrap items-center gap-x-3 gap-y-1 rounded px-2 py-1.5 hover:bg-app">
                  <input type="checkbox" checked={selected.has(c.index)} onChange={() => toggle(c.index)} className="size-4 accent-teal" />
                  <span className="font-medium">{c.title}</span>
                  <span className="text-body-s text-ink-500">
                    trang {c.startPage}–{c.endPage} ({c.pages} trang)
                  </span>
                  {keep.has(c.index) && (
                    <span className="inline-flex items-center gap-1 rounded-full border border-line-strong bg-st-pass px-2 text-body-s">
                      <Check aria-hidden size={12} /> Nên giữ
                    </span>
                  )}
                  {skipReason.has(c.index) && (
                    <span className="inline-flex items-center gap-1 rounded-full border border-line-strong bg-st-grey px-2 text-body-s">
                      <X aria-hidden size={12} /> Nên bỏ: {skipReason.get(c.index)}
                    </span>
                  )}
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
      ) : (
        <div className="space-y-1">
          <label htmlFor="page-ranges" className="block font-semibold">
            Khoảng trang cần dựng cây
          </label>
          <input
            id="page-ranges"
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={!report.gated || busy}
            placeholder="ví dụ 10-45, 60-80"
            aria-describedby="page-ranges-help"
            className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-body-m"
          />
          <p id="page-ranges-help" className="text-body-s text-ink-500">
            Trang trong tệp, từ 1 đến {report.totalPages}. Hệ thống không xác định được trang của từng chương nên thầy/cô nhập khoảng trang trọng tâm.
          </p>
        </div>
      )}

      <fieldset className="space-y-2" disabled={locked}>
        <legend className="mb-1 font-semibold">Mức chi tiết của cây</legend>
        <div className="grid gap-2 sm:grid-cols-3">
          {DETAILS.map((d) => (
            <label key={d.key} className="flex cursor-pointer items-start gap-2 rounded-md border border-line-strong bg-surface p-3 has-[:checked]:border-teal has-[:checked]:bg-teal-soft">
              <input type="radio" name="detail" checked={detail === d.key} onChange={() => setDetail(d.key)} className="mt-1 size-4 accent-teal" />
              <span>
                <span className="block font-medium">{d.label}</span>
                <span className="block text-body-s text-ink-500">
                  {d.hint} · tối đa {report.detailCaps?.[d.key]} khái niệm/đoạn
                </span>
                <span className="block text-body-s font-semibold">~{estimateScope(report, chunks, d.key, lazyRubric).nodes} nút</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <label className="flex cursor-pointer items-start gap-2 rounded-md border border-line-strong bg-surface p-3">
        <input type="checkbox" checked={lazyRubric} disabled={locked} onChange={(e) => setLazyRubric(e.target.checked)} className="mt-1 size-4 accent-teal" />
        <span>
          <span className="block font-medium">Chưa sinh rubric lúc dựng cây</span>
          <span className="block text-body-s text-ink-500">
            Tiết kiệm khoảng một nửa lượt gọi AI. Sau khi dựng, thầy/cô bỏ bớt nút ở trình sửa cây rồi bấm “Sinh rubric cho nút còn thiếu”. Phát hành cây vẫn cần mọi rubric đã duyệt.
          </span>
        </span>
      </label>

      {invalid && <ErrorBox text={invalid} />}
      {error !== undefined && <ErrorBox text={error instanceof Error ? error.message : "Không dựng được cây, hãy thử lại."} />}

      {report.gated ? (
        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={!canBuild} onClick={() => onBuild({ ranges, detail, lazyRubric })}>
            {busy ? "Đang gửi…" : "Dựng cây từ phần đã chọn"}
          </Button>
          <Button variant="secondary" disabled={busy} onClick={() => onBuild({ ranges: [], detail, lazyRubric })}>
            Dựng từ toàn bộ giáo trình
          </Button>
          <span role="status" className="text-body-s text-ink-500">
            {ranges.length > 0
              ? `Đã chọn ${chosenPages} / ${report.totalPages} trang · dự kiến ~${est.nodes} nút, ~${est.calls} lượt gọi AI`
              : "Chưa chọn phần nào"}
          </span>
        </div>
      ) : (
        <p className="text-body-s text-ink-500">Đang dựng cây theo lựa chọn của thầy/cô.</p>
      )}
    </section>
  );
}
