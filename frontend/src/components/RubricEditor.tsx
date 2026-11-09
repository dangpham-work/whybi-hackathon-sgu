import { Check, CircleCheck, Clock, Plus, Sparkles, Trash2, TriangleAlert } from "lucide-react";
import { useState } from "react";
import type { Rubric } from "../lib/tree-edit";
import { rubricProblems } from "../lib/tree-edit";
import { Button } from "./Button";

const field = "w-full rounded-md border border-line-strong px-3 py-2 text-body-m focus-visible:outline-2 focus-visible:outline-teal";

/**
 * Sửa rubric một nút (FR-SK-08, GD-09): ý chính bắt buộc, quan niệm sai, ngưỡng; lưu, duyệt, sinh lại bằng AI.
 * Sửa xong và lưu thì rubric về trạng thái chưa duyệt – phải bấm Duyệt rubric (BR-05).
 */
export function RubricEditor({
  rubric,
  busy,
  onSave,
  onRegenerate,
}: {
  rubric: Rubric;
  busy: boolean;
  onSave: (r: Rubric) => void;
  onRegenerate: () => void;
}) {
  const [r, setR] = useState(rubric);
  const dirty = JSON.stringify(r) !== JSON.stringify(rubric);
  const set = (patch: Partial<Rubric>) => setR((x) => ({ ...x, ...patch }));
  const nextId = (prefix: string, ids: string[]) => {
    let i = ids.length + 1;
    while (ids.includes(`${prefix}${i}`)) i++;
    return `${prefix}${i}`;
  };

  const problems = rubricProblems(r);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between border-b border-line-soft pb-2">
        <h3 className="caps text-ink-700">Tiêu chí đánh giá (Rubric)</h3>
        {r.approved && !dirty ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-teal-soft px-2 py-0.5 text-body-s font-semibold text-teal">
            <CircleCheck size={12} /> Đã duyệt
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full bg-honey-soft px-2 py-0.5 text-body-s font-semibold text-honey-deep">
            <Clock size={12} /> Chưa duyệt
          </span>
        )}
      </div>

      <section aria-label="Ý chính" className="space-y-2">
        <div className="flex items-center justify-between">
          <h4 className="caps text-ink-700">Ý chính bắt buộc ({r.keyPoints.filter((k) => k.isRequired).length}/{r.keyPoints.length})</h4>
          <span className="text-body-s text-ink-400">Tích chọn để bắt buộc</span>
        </div>
        {r.keyPoints.map((k, i) => (
          <div key={k.id} className="flex items-center gap-2">
            <input
              type="checkbox"
              aria-label={`Ý ${k.id} bắt buộc`}
              title="Ý này bắt buộc phải đạt"
              checked={k.isRequired}
              className="size-4 rounded border-line-strong text-teal focus:ring-teal"
              onChange={(e) => set({ keyPoints: r.keyPoints.map((x, j) => (j === i ? { ...x, isRequired: e.target.checked } : x)) })}
            />
            <input
              aria-label={`Nội dung ý ${k.id}`}
              className={field}
              placeholder="Nội dung tiêu chí cần đạt..."
              value={k.content}
              onChange={(e) => set({ keyPoints: r.keyPoints.map((x, j) => (j === i ? { ...x, content: e.target.value } : x)) })}
            />
            <button
              type="button"
              aria-label={`Xóa ý ${k.id}`}
              title="Xóa ý này"
              onClick={() => set({ keyPoints: r.keyPoints.filter((_, j) => j !== i) })}
              className="p-1 text-ink-400 hover:text-red-700 transition"
            >
              <Trash2 aria-hidden size={16} />
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() => set({ keyPoints: [...r.keyPoints, { id: nextId("KP", r.keyPoints.map((k) => k.id)), content: "", isRequired: true }] })}
          className="inline-flex items-center gap-1 text-body-m font-semibold text-teal hover:underline"
        >
          <Plus aria-hidden size={16} /> Thêm ý chính
        </button>
      </section>

      <section aria-label="Quan niệm sai" className="space-y-2">
        <h4 className="caps text-ink-700">Quan niệm sai thường gặp ({r.misconceptions.length})</h4>
        {r.misconceptions.map((m, i) => (
          <div key={m.id} className="flex items-center gap-2">
            <input
              aria-label={`Quan niệm sai ${m.id}`}
              className={field}
              placeholder="Quan niệm sai hoặc lỗi phổ biến..."
              value={m.content}
              onChange={(e) => set({ misconceptions: r.misconceptions.map((x, j) => (j === i ? { ...x, content: e.target.value } : x)) })}
            />
            <button
              type="button"
              aria-label={`Xóa quan niệm sai ${m.id}`}
              title="Xóa quan niệm sai này"
              onClick={() => set({ misconceptions: r.misconceptions.filter((_, j) => j !== i) })}
              className="p-1 text-ink-400 hover:text-red-700 transition"
            >
              <Trash2 aria-hidden size={16} />
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() => set({ misconceptions: [...r.misconceptions, { id: nextId("MC", r.misconceptions.map((m) => m.id)), content: "", isCritical: false }] })}
          className="inline-flex items-center gap-1 text-body-m font-semibold text-teal hover:underline"
        >
          <Plus aria-hidden size={16} /> Thêm quan niệm sai
        </button>
      </section>

      <div className="grid grid-cols-2 gap-3">
        <label className="space-y-1 text-body-s font-semibold text-ink-700">
          <span>Số câu phản biện</span>
          <input type="number" min={1} className={field} value={r.minChallenges} onChange={(e) => set({ minChallenges: Number(e.target.value) })} />
        </label>
        <label className="space-y-1 text-body-s font-semibold text-ink-700">
          <span>Ngưỡng Đạt (/100)</span>
          <input type="number" min={0} max={100} className={field} value={r.passThreshold} onChange={(e) => set({ passThreshold: Number(e.target.value) })} />
        </label>
      </div>

      {r.scenarios.length > 0 && (
        <section aria-label="Tình huống phản biện" className="space-y-1">
          <h4 className="caps text-ink-700">Tình huống phản biện</h4>
          <ul className="list-disc space-y-1 pl-5 text-body-m text-ink-700">
            {r.scenarios.map((s) => (
              <li key={s.id}>{s.scenario}</li>
            ))}
          </ul>
        </section>
      )}

      {r.sourcePages.length > 0 && (
        <p className="rounded-md bg-app px-3 py-2 text-body-s text-ink-500">
          Trích dẫn giáo trình: <strong>tr. {r.sourcePages.join(", ")}</strong>
        </p>
      )}

      {problems.length > 0 && (
        <div role="alert" className="flex items-center gap-2 rounded-md bg-honey-soft px-3 py-2 text-body-s font-medium text-honey-deep">
          <TriangleAlert size={16} className="shrink-0" />
          <span>Chưa đủ điều kiện duyệt: {problems.join("; ")}</span>
        </div>
      )}

      <div className="space-y-2 pt-2">
        <Button
          variant="teal"
          className="w-full justify-center"
          disabled={busy || problems.length > 0 || (r.approved && !dirty)}
          title={problems.length > 0 ? `Chưa thể duyệt: ${problems.join("; ")}` : undefined}
          onClick={() => onSave({ ...r, approved: true })}
        >
          <Check aria-hidden size={16} /> {r.approved && !dirty ? "Đã duyệt rubric" : "Duyệt rubric"}
        </Button>
        <div className="grid grid-cols-2 gap-2">
          <Button variant="secondary" className="justify-center" disabled={busy} onClick={onRegenerate}>
            <Sparkles aria-hidden size={16} /> Sinh lại AI
          </Button>
          <Button variant="secondary" className="justify-center" disabled={busy || !dirty} onClick={() => onSave({ ...r, approved: false })}>
            Lưu nháp
          </Button>
        </div>
      </div>
    </div>
  );
}
