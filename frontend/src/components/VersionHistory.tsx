import { History, RotateCcw } from "lucide-react";
import { useState } from "react";
import { apiCall, errorText, type Schema } from "../lib/api";
import { TREE_STATUS } from "../lib/status";
import { useApi } from "../lib/useApi";
import { AsyncView, ErrorBox } from "./AsyncView";
import { Button } from "./Button";

type Version = Schema<"TreeVersion">;
type VersionSummary = Schema<"TreeVersionSummary">;
type Diff = Schema<"TreeDiff">;

const vn = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" }) : "");

/**
 * Lịch sử phiên bản cây (FR-SK-10, GD-14): danh sách, so sánh hai bản theo key nút, tạo bản nháp mới từ một bản cũ (#197).
 * `onRestored` nhận bản nháp vừa tạo để GV-04 chuyển sang sửa tiếp.
 */
export function VersionHistory({
  classId,
  currentDraftVersionNo,
  nodeTitle,
  onRestored,
}: {
  classId: string;
  currentDraftVersionNo?: number | null;
  nodeTitle: (key: string) => string;
  onRestored: (draft: Version, fromVersionNo: number) => void;
}) {
  const versions = useApi((signal) => apiCall("get", "/classes/{class_id}/tree-versions", { path: { class_id: classId }, signal }), [classId]);
  const [picked, setPicked] = useState<string[]>([]);
  const [diff, setDiff] = useState<Diff>();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>();

  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id].slice(-2)));
  async function run<T>(fn: () => Promise<T>, then: (r: T) => void) {
    setBusy(true);
    setFailure(undefined);
    try {
      then(await fn());
    } catch (e) {
      setFailure(e);
    } finally {
      setBusy(false);
    }
  }
  const compare = (list: VersionSummary[]) => {
    // luôn so bản cũ → bản mới
    const [a, b] = picked.map((id) => list.find((v) => v.id === id)!).sort((x, y) => x.versionNo - y.versionNo);
    return run(() => apiCall("get", "/tree-versions/{from_id}/compare/{to_id}", { path: { from_id: a.id!, to_id: b.id! } }), setDiff);
  };

  return (
    <section aria-label="Lịch sử phiên bản" className="space-y-3 rounded-lg border border-line-soft bg-surface p-4">
      <h2 className="flex items-center gap-2 text-h3 font-semibold">
        <History aria-hidden size={18} /> Lịch sử phiên bản
      </h2>
      {failure !== undefined && <ErrorBox text={errorText(failure)} />}
      <AsyncView state={versions} isEmpty={(l) => l.length === 0} empty="Chưa có phiên bản nào.">
        {(list) => (
          <>
            <ul className="divide-y divide-line-soft">
              {list.map((v) => {
                const look = TREE_STATUS[v.status];
                const Icon = look.icon;
                return (
                  <li key={v.id} className="flex flex-wrap items-center gap-3 py-2">
                    <label className="flex flex-1 items-center gap-2">
                      <input type="checkbox" aria-label={`Chọn v${v.versionNo} để so sánh`} checked={picked.includes(v.id!)} onChange={() => toggle(v.id!)} />
                      <span className="font-semibold">v{v.versionNo}</span>
                      <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-body-s font-semibold ${look.className}`}>
                        <Icon aria-hidden size={12} /> {look.label}
                      </span>
                      <span className="text-body-s text-ink-500">{vn(v.publishedAt)}</span>
                      {v.changeNote && <span className="text-body-s text-ink-500">· {v.changeNote}</span>}
                    </label>
                    <button
                      type="button"
                      disabled={busy || (currentDraftVersionNo != null && v.versionNo === currentDraftVersionNo)}
                      aria-label={`Tạo bản nháp từ v${v.versionNo}`}
                      onClick={() =>
                        run(
                          () => apiCall("post", "/tree-versions/{version_id}/restore", { path: { version_id: v.id! } }),
                          (draft) => onRestored(draft, v.versionNo),
                        )
                      }
                      className="inline-flex items-center gap-1 rounded-md border border-line-strong px-2 py-1 text-body-s font-semibold disabled:opacity-50"
                    >
                      <RotateCcw aria-hidden size={14} /> Tạo bản nháp từ v{v.versionNo}
                    </button>
                  </li>
                );
              })}
            </ul>
            <Button variant="secondary" disabled={busy || picked.length !== 2} onClick={() => compare(list)}>
              So sánh 2 phiên bản đã chọn
            </Button>
          </>
        )}
      </AsyncView>
      {diff && <DiffView d={diff} title={nodeTitle} />}
    </section>
  );
}

function DiffView({ d, title }: { d: Diff; title: (k: string) => string }) {
  const none = !d.nodesAdded.length && !d.nodesRemoved.length && !d.nodesChanged.length && !d.edgesAdded.length && !d.edgesRemoved.length;
  const edge = (e: { fromKey: string; toKey: string }) => `${title(e.fromKey)} → ${title(e.toKey)}`;
  return (
    <div role="region" aria-label="Kết quả so sánh" className="space-y-1 rounded-md bg-app p-3 text-body-m">
      <p className="font-semibold">
        So sánh v{d.fromVersionNo} → v{d.toVersionNo}
      </p>
      {none && <p>Hai phiên bản giống nhau.</p>}
      <Group label="Nút thêm" items={d.nodesAdded.map(title)} tone="text-green-800" />
      <Group label="Nút bỏ" items={d.nodesRemoved.map(title)} tone="text-red-800" />
      <Group label="Nút đổi" items={d.nodesChanged.map(title)} tone="text-honey-deep" />
      <Group label="Cạnh thêm" items={d.edgesAdded.map(edge)} tone="text-green-800" />
      <Group label="Cạnh bỏ" items={d.edgesRemoved.map(edge)} tone="text-red-800" />
    </div>
  );
}

function Group({ label, items, tone }: { label: string; items: string[]; tone: string }) {
  if (items.length === 0) return null;
  return (
    <p>
      <span className={`font-semibold ${tone}`}>
        {label} ({items.length}):
      </span>{" "}
      {items.join(", ")}
    </p>
  );
}
