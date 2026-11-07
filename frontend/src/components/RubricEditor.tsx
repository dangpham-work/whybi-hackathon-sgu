import { Check, Plus, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";
import type { Rubric } from "../lib/tree-edit";
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

  return (
    <div className="space-y-4">
      <section aria-label="Ý chính" className="space-y-2">
        <h3 className="caps">Ý chính bắt buộc ({r.keyPoints.filter((k) => k.isRequired).length})</h3>
        {r.keyPoints.map((k, i) => (
          <div key={k.id} className="flex items-center gap-2">
            <input
              type="checkbox"
              aria-label={`Ý ${k.id} bắt buộc`}
              checked={k.isRequired}
              onChange={(e) => set({ keyPoints: r.keyPoints.map((x, j) => (j === i ? { ...x, isRequired: e.target.checked } : x)) })}
            />
            <input
              aria-label={`Nội dung ý ${k.id}`}
              className={field}
              value={k.content}
              onChange={(e) => set({ keyPoints: r.keyPoints.map((x, j) => (j === i ? { ...x, content: e.target.value } : x)) })}
            />
            <button type="button" aria-label={`Xóa ý ${k.id}`} onClick={() => set({ keyPoints: r.keyPoints.filter((_, j) => j !== i) })} className="p-1 text-ink-500 hover:text-red-700">
              <Trash2 aria-hidden size={16} />
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() => set({ keyPoints: [...r.keyPoints, { id: nextId("KP", r.keyPoints.map((k) => k.id)), content: "", isRequired: true }] })}
          className="inline-flex items-center gap-1 text-body-m font-semibold text-teal"
        >
          <Plus aria-hidden size={16} /> Thêm ý chính
        </button>
      </section>

      <section aria-label="Quan niệm sai" className="space-y-2">
        <h3 className="caps">Quan niệm sai thường gặp</h3>
        {r.misconceptions.map((m, i) => (
          <div key={m.id} className="flex items-center gap-2">
            <input
              aria-label={`Quan niệm sai ${m.id}`}
              className={field}
              value={m.content}
              onChange={(e) => set({ misconceptions: r.misconceptions.map((x, j) => (j === i ? { ...x, content: e.target.value } : x)) })}
            />
            <button type="button" aria-label={`Xóa quan niệm sai ${m.id}`} onClick={() => set({ misconceptions: r.misconceptions.filter((_, j) => j !== i) })} className="p-1 text-ink-500 hover:text-red-700">
              <Trash2 aria-hidden size={16} />
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() => set({ misconceptions: [...r.misconceptions, { id: nextId("MC", r.misconceptions.map((m) => m.id)), content: "", isCritical: false }] })}
          className="inline-flex items-center gap-1 text-body-m font-semibold text-teal"
        >
          <Plus aria-hidden size={16} /> Thêm quan niệm sai
        </button>
      </section>

      <div className="grid grid-cols-2 gap-3">
        <label className="space-y-1 text-body-s font-semibold">
          Số câu phản biện
          <input type="number" min={1} className={field} value={r.minChallenges} onChange={(e) => set({ minChallenges: Number(e.target.value) })} />
        </label>
        <label className="space-y-1 text-body-s font-semibold">
          Ngưỡng Đạt (/100)
          <input type="number" min={0} max={100} className={field} value={r.passThreshold} onChange={(e) => set({ passThreshold: Number(e.target.value) })} />
        </label>
      </div>
      {r.scenarios.length > 0 && (
        <section aria-label="Tình huống phản biện" className="space-y-1">
          <h3 className="caps">Tình huống phản biện</h3>
          <ul className="list-disc space-y-1 pl-5 text-body-m">
            {r.scenarios.map((s) => (
              <li key={s.id}>{s.scenario}</li>
            ))}
          </ul>
        </section>
      )}
      {r.sourcePages.length > 0 && <p className="rounded-md bg-app px-3 py-2 text-body-s">Trích dẫn giáo trình: tr. {r.sourcePages.join(", ")}</p>}

      <div className="grid grid-cols-3 gap-2">
        <Button variant="secondary" disabled={busy} onClick={onRegenerate}>
          <Sparkles aria-hidden size={16} /> Sinh lại AI
        </Button>
        <Button variant="secondary" disabled={busy || !dirty} onClick={() => onSave({ ...r, approved: false })}>
          Lưu nháp
        </Button>
        <Button variant="teal" disabled={busy || (r.approved && !dirty)} onClick={() => onSave({ ...r, approved: true })}>
          <Check aria-hidden size={16} /> {r.approved && !dirty ? "Đã duyệt" : "Duyệt rubric"}
        </Button>
      </div>
    </div>
  );
}
