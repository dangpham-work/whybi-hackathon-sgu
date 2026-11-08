import { Flag, GitMerge, History, Plus, Trash2, TriangleAlert, CircleCheck, Lock } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router";
import { AsyncView, ErrorBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { RubricEditor } from "../../components/RubricEditor";
import { VersionHistory } from "../../components/VersionHistory";
import { SkillTree, BLOOM_LABEL } from "../../components/SkillTree";
import { apiCall, errorText, type Schema } from "../../lib/api";
import {
  autoConnectedOnDelete,
  cycleMessage,
  emptyRubric,
  isEditable,
  newNodeKey,
  publishErrorItems,
  unapproved,
  type PublishErrorItem,
  type Rubric,
  type TreeVersion,
} from "../../lib/tree-edit";
import { useApi } from "../../lib/useApi";

const field = "w-full rounded-md border border-line-strong px-3 py-2 text-body-m focus-visible:outline-2 focus-visible:outline-teal";

/** GV-04 Trình sửa cây & rubric (Figma 17:1065, FR-SK-04…09, GD-09). Lịch sử / so sánh phiên bản: GD-14. */
export default function LecturerTreeEditor() {
  const { classId = "" } = useParams();
  const tree = useApi((signal) => apiCall("get", "/classes/{class_id}/tree", { path: { class_id: classId }, query: { draft: true }, signal }), [classId]);
  return (
    <div className="space-y-4 p-4 lg:p-7">
      <h1 className="text-h1 font-bold">Trình sửa cây & rubric</h1>
      <AsyncView state={tree} loadingText="Đang tải cây kỹ năng…">
        {(t) => <Editor key={t.id ?? t.versionNo} initial={t} classId={classId} />}
      </AsyncView>
    </div>
  );
}

function Editor({ initial, classId }: { initial: TreeVersion; classId: string }) {
  const [tree, setTree] = useState(initial);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: "error" | "ok"; items: PublishErrorItem[] }>();
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [merging, setMerging] = useState(false);
  const [history, setHistory] = useState(false);
  const [title, setTitle] = useState("");
  const editable = isEditable(tree);
  const selected = tree.nodes.find((n) => n.key === selectedKey);
  const missing = unapproved(tree);
  const nodeTitle = (key: string) => tree.nodes.find((n) => n.key === key)?.title ?? key;

  /** Chạy một thao tác ghi: báo lỗi dễ hiểu, không làm mất bản vẽ hiện tại. */
  async function run(action: () => Promise<void>, onError?: (e: unknown) => PublishErrorItem[] | null) {
    setBusy(true);
    setMessage(undefined);
    try {
      await action();
    } catch (e) {
      setMessage({ kind: "error", items: onError?.(e) ?? [{ text: errorText(e) }] });
    } finally {
      setBusy(false);
    }
  }
  const patchNode = (key: string, f: (n: Schema<"Node">) => Schema<"Node">) =>
    setTree((t) => ({ ...t, nodes: t.nodes.map((n) => (n.key === key ? f(n) : n)) }));

  const makeDraft = () =>
    run(async () => {
      const draft = await apiCall("post", "/classes/{class_id}/tree-versions", { path: { class_id: classId } });
      setTree(draft);
    });

  const addNode = () =>
    run(async () => {
      const node = await apiCall("post", "/tree-versions/{version_id}/nodes", {
        path: { version_id: tree.id! },
        body: { key: newNodeKey(tree.nodes), title: title.trim(), bloomLevel: "UNDERSTAND", rubric: emptyRubric() },
      });
      setTree((t) => ({ ...t, nodes: [...t.nodes, node] }));
      setTitle("");
      setAdding(false);
      setSelectedKey(node.key);
    });

  const confirmDeleteNode = () => {
    if (!selected?.id) return;
    const removedTitle = selected.title;
    void run(async () => {
      const updated = await apiCall("delete", "/nodes/{node_id}", { path: { node_id: selected.id! } });
      setTree(updated);
      setSelectedKey(null);
      setDeleting(false);
      setMessage({ kind: "ok", items: [{ text: `Đã xóa nút "${removedTitle}".` }] });
    });
  };

  const confirmMergeNodes = (body: Schema<"MergeNodesIn">) =>
    run(
      async () => {
        const updated = await apiCall("post", "/tree-versions/{version_id}/merge-nodes", {
          path: { version_id: tree.id! },
          body,
        });
        setTree(updated);
        setSelectedKey(body.firstKey);
        setMerging(false);
        setMessage({ kind: "ok", items: [{ text: "Đã gộp hai nút thành công." }] });
      },
      (e) => [{ text: cycleMessage(e, tree.nodes) ?? errorText(e) }],
    );

  const connect = (from: string, to: string) =>
    run(
      async () => {
        const edge = await apiCall("post", "/tree-versions/{version_id}/edges", { path: { version_id: tree.id! }, body: { fromKey: from, toKey: to, source: "LECTURER" } });
        setTree((t) => ({ ...t, edges: [...t.edges, edge] }));
      },
      (e) => [{ text: cycleMessage(e, tree.nodes) ?? errorText(e) }],
    );

  const removeEdge = (id: string) =>
    run(async () => {
      await apiCall("delete", "/edges/{edge_id}", { path: { edge_id: id } });
      setTree((t) => ({ ...t, edges: t.edges.filter((e) => e.id !== id) }));
    });

  const move = (key: string, pos: { x: number; y: number }) => {
    const n = tree.nodes.find((x) => x.key === key);
    if (!n?.id) return;
    patchNode(key, (x) => ({ ...x, positionX: pos.x, positionY: pos.y }));
    void apiCall("patch", "/nodes/{node_id}", { path: { node_id: n.id }, body: { positionX: pos.x, positionY: pos.y } }).catch(() => {});
  };

  const saveBasics = (n: Schema<"Node">) =>
    run(async () => {
      const saved = await apiCall("patch", "/nodes/{node_id}", {
        path: { node_id: n.id! },
        body: { title: n.title, chapterRef: n.chapterRef, bloomLevel: n.bloomLevel },
      });
      patchNode(n.key, (x) => ({ ...x, ...saved, rubric: x.rubric }));
      setMessage({ kind: "ok", items: [{ text: "Đã lưu thông tin nút." }] });
    });

  const saveRubric = (n: Schema<"Node">, r: Rubric) =>
    run(async () => {
      const saved = await apiCall("put", "/nodes/{node_id}/rubric", { path: { node_id: n.id! }, body: r });
      patchNode(n.key, (x) => ({ ...x, rubric: saved }));
      setMessage({ kind: "ok", items: [{ text: saved.approved ? "Đã duyệt rubric." : "Đã lưu rubric (chưa duyệt)." }] });
    });

  const regenerate = (n: Schema<"Node">) =>
    run(async () => {
      const fresh = await apiCall("post", "/nodes/{node_id}/rubric/regenerate", { path: { node_id: n.id! } });
      patchNode(n.key, (x) => ({ ...x, rubric: fresh }));
      setMessage({ kind: "ok", items: [{ text: "AI đã sinh lại rubric – hãy xem và duyệt." }] });
    });

  const publish = () =>
    run(
      async () => {
        const done = await apiCall("post", "/tree-versions/{version_id}/publish", { path: { version_id: tree.id! } });
        setTree(done);
        setMessage({ kind: "ok", items: [{ text: `Đã phát hành phiên bản v${done.versionNo} cho lớp.` }] });
      },
      (e) => publishErrorItems(e) ?? [{ text: errorText(e) }],
    );

  return (
    <>
      <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Công cụ sửa cây">
        <Button variant="secondary" disabled={!editable || busy} onClick={() => setAdding((a) => !a)}>
          <Plus aria-hidden size={16} /> Thêm nút
        </Button>
        <Button
          variant="secondary"
          disabled={!editable || busy || !selected?.id}
          title={selected ? `Xóa nút ${selected.title}` : "Chọn một nút trên cây để xóa"}
          onClick={() => setDeleting((d) => !d)}
        >
          <Trash2 aria-hidden size={16} /> Xóa nút
        </Button>
        <Button
          variant="secondary"
          disabled={!editable || busy || tree.nodes.length < 2}
          onClick={() => setMerging((m) => !m)}
        >
          <GitMerge aria-hidden size={16} /> Gộp nút
        </Button>
        <Button variant="secondary" aria-pressed={history} onClick={() => setHistory((h) => !h)}>
          <History aria-hidden size={16} /> Lịch sử
        </Button>
        <span className="ml-auto text-body-s text-ink-500">{`v${tree.versionNo} · ${editable ? "Bản nháp" : tree.status === "PUBLISHED" ? "Đã phát hành" : tree.status}`}</span>
        <Button disabled={!editable || busy} onClick={publish}>
          <Flag aria-hidden size={16} /> Phát hành
        </Button>
      </div>

      {!editable && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-honey/50 bg-honey-soft p-3 text-body-m text-honey-deep">
          <Lock aria-hidden size={16} /> Phiên bản này không sửa được.
          <Button variant="secondary" disabled={busy} onClick={makeDraft}>
            Tạo bản nháp để sửa
          </Button>
        </div>
      )}
      {adding && (
        <form
          className="flex items-end gap-2 rounded-lg border border-line-soft bg-surface p-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (title.trim()) void addNode();
          }}
        >
          <label className="flex-1 space-y-1 text-body-s font-semibold">
            Tên nút mới
            <input className={field} value={title} onChange={(e) => setTitle(e.target.value)} autoFocus />
          </label>
          <Button type="submit" disabled={!title.trim() || busy}>
            Thêm
          </Button>
        </form>
      )}
      {deleting && selected && (
        <DeleteNodeDialog
          node={selected}
          autoEdges={autoConnectedOnDelete(tree, selected.key)}
          nodeTitle={nodeTitle}
          busy={busy}
          onConfirm={confirmDeleteNode}
          onCancel={() => setDeleting(false)}
        />
      )}
      {merging && tree.nodes.length >= 2 && (
        <MergeNodesDialog
          nodes={tree.nodes}
          defaultFirstKey={selectedKey ?? tree.nodes[0]!.key}
          busy={busy}
          onConfirm={(b) => void confirmMergeNodes(b)}
          onCancel={() => setMerging(false)}
        />
      )}
      {message &&
        (message.kind === "error" ? (
          message.items.length === 1 && !message.items[0]?.nodeKey ? (
            <ErrorBox text={message.items[0]!.text} />
          ) : (
            <div role="alert" className="space-y-1 rounded-lg border border-red-700/40 bg-st-fail/40 p-4 text-body-m text-red-900">
              <ul className="list-disc space-y-1 pl-5 text-body-s">
                {message.items.map((item, idx) => (
                  <li key={`${item.nodeKey ?? idx}-${item.text}`}>
                    {item.nodeKey ? (
                      <button
                        type="button"
                        onClick={() => setSelectedKey(item.nodeKey!)}
                        className="text-left font-medium underline hover:text-ink-900"
                      >
                        {item.text}
                      </button>
                    ) : (
                      item.text
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )
        ) : (
          <p role="status" className="flex items-center gap-2 text-body-m text-teal">
            <CircleCheck aria-hidden size={16} />
            {message.items.map((i) => i.text).join(" ")}
          </p>
        ))}

      {history && (
        <VersionHistory
          classId={classId}
          currentDraftVersionNo={editable ? tree.versionNo : null}
          nodeTitle={nodeTitle}
          onRestored={(draft, fromVersionNo) => {
            setTree(draft);
            setSelectedKey(null);
            setHistory(false);
            setMessage({
              kind: "ok",
              items: [{ text: `Đã tạo bản nháp v${draft.versionNo} (Tạo bản nháp từ v${fromVersionNo}) – duyệt lại rubric rồi phát hành.` }],
            });
          }}
        />
      )}

      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        <section aria-label="Khung vẽ cây" className="space-y-3 rounded-lg border border-line-soft bg-surface p-4">
          <p className="text-body-s text-ink-500">Kéo từ mép nút để tạo cạnh tiên quyết · thao tác tạo chu trình sẽ bị chặn (BR-01).</p>
          <SkillTree
            mode="edit"
            nodes={tree.nodes}
            edges={tree.edges}
            selectedKey={selectedKey}
            height={420}
            onNodeClick={(n) => setSelectedKey(n.key)}
            onNodeMove={editable ? move : undefined}
            onConnect={editable ? connect : undefined}
          />
          <div className="flex flex-wrap items-center justify-between gap-2 text-body-s">
            {missing.length > 0 ? (
              <p className="flex items-center gap-2 rounded-md bg-honey-soft px-3 py-2 font-semibold text-honey-deep">
                <TriangleAlert aria-hidden size={14} /> {missing.length} nút chưa duyệt rubric: {missing.map((n) => n.code ?? n.title).join(", ")} – chưa thể phát hành (BR-05)
              </p>
            ) : (
              <p className="flex items-center gap-2 font-semibold text-teal">
                <CircleCheck aria-hidden size={14} /> Mọi rubric đã duyệt
              </p>
            )}
            <span className="text-teal">{`${tree.nodes.length} nút · ${tree.edges.length} cạnh`}</span>
          </div>
        </section>

        <aside aria-label="Thuộc tính nút" className="space-y-4 rounded-lg border border-line-soft bg-surface p-4">
          {selected ? (
            <NodePanel
              key={selected.key}
              node={selected}
              tree={tree}
              editable={editable}
              busy={busy}
              onSaveBasics={saveBasics}
              onSaveRubric={(r) => saveRubric(selected, r)}
              onRegenerate={() => regenerate(selected)}
              onRemoveEdge={removeEdge}
            />
          ) : (
            <p className="text-body-m text-ink-500">Chọn một nút trên cây để sửa thông tin và rubric.</p>
          )}
        </aside>
      </div>
    </>
  );
}

function NodePanel({
  node,
  tree,
  editable,
  busy,
  onSaveBasics,
  onSaveRubric,
  onRegenerate,
  onRemoveEdge,
}: {
  node: Schema<"Node">;
  tree: TreeVersion;
  editable: boolean;
  busy: boolean;
  onSaveBasics: (n: Schema<"Node">) => void;
  onSaveRubric: (r: Rubric) => void;
  onRegenerate: () => void;
  onRemoveEdge: (id: string) => void;
}) {
  const [draft, setDraft] = useState(node);
  const name = (key: string) => tree.nodes.find((n) => n.key === key)?.title ?? key;
  const incoming = tree.edges.filter((e) => e.toKey === node.key);
  return (
    <>
      <div className="flex items-center justify-between">
        <h2 className="caps">Thuộc tính nút</h2>
        <span className="rounded-full bg-app px-2 py-0.5 text-body-s font-semibold">{node.code ?? node.key}</span>
      </div>
      <label className="block space-y-1 text-body-s font-semibold">
        Tên nút
        <input className={field} value={draft.title} disabled={!editable} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
      </label>
      <div className="grid grid-cols-2 gap-3">
        <label className="space-y-1 text-body-s font-semibold">
          Chương
          <input className={field} value={draft.chapterRef ?? ""} disabled={!editable} onChange={(e) => setDraft({ ...draft, chapterRef: e.target.value })} />
        </label>
        <label className="space-y-1 text-body-s font-semibold">
          Mức Bloom
          <select className={field} value={draft.bloomLevel} disabled={!editable} onChange={(e) => setDraft({ ...draft, bloomLevel: e.target.value as typeof draft.bloomLevel })}>
            {Object.entries(BLOOM_LABEL).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
      </div>
      {editable && (
        <Button variant="secondary" disabled={busy || !draft.title.trim()} onClick={() => onSaveBasics(draft)}>
          Lưu thông tin nút
        </Button>
      )}

      <section aria-label="Tiên quyết" className="space-y-1">
        <h3 className="caps">Tiên quyết</h3>
        {incoming.length === 0 && <p className="text-body-s text-ink-500">Nút gốc – không có tiên quyết.</p>}
        {incoming.map((e) => (
          <div key={e.id ?? e.fromKey} className="flex items-center justify-between text-body-m">
            {name(e.fromKey)}
            {editable && e.id && (
              <button type="button" aria-label={`Xóa cạnh từ ${name(e.fromKey)}`} onClick={() => onRemoveEdge(e.id!)} className="p-1 text-ink-500 hover:text-red-700">
                <Trash2 aria-hidden size={16} />
              </button>
            )}
          </div>
        ))}
      </section>

      {editable && node.id ? (
        <RubricEditor key={JSON.stringify(node.rubric)} rubric={node.rubric ?? emptyRubric()} busy={busy} onSave={onSaveRubric} onRegenerate={onRegenerate} />
      ) : (
        <p className="text-body-s text-ink-500">Rubric: {node.rubric?.approved ? "đã duyệt" : "chưa duyệt"} ({node.rubric?.keyPoints.length ?? 0} ý chính).</p>
      )}
    </>
  );
}

function DeleteNodeDialog({
  node,
  autoEdges,
  nodeTitle,
  busy,
  onConfirm,
  onCancel,
}: {
  node: Schema<"Node">;
  autoEdges: { fromKey: string; toKey: string }[];
  nodeTitle: (key: string) => string;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div role="dialog" aria-label="Xác nhận xóa nút" className="space-y-3 rounded-lg border border-red-700/40 bg-surface p-4 shadow-card">
      <p className="text-body-m font-semibold text-red-900">
        Xóa nút “{node.title}” ({node.code ?? node.key})? Thông tin và rubric của nút này sẽ bị xóa.
      </p>
      {autoEdges.length > 0 ? (
        <p className="text-body-s text-ink-700">
          Các cạnh tiên quyết sẽ được nối thêm: {autoEdges.map((e) => `${nodeTitle(e.fromKey)} → ${nodeTitle(e.toKey)}`).join(", ")}.
        </p>
      ) : (
        <p className="text-body-s text-ink-500">Không có cạnh bắc cầu nào cần nối thêm.</p>
      )}
      <div className="flex gap-2">
        <Button variant="secondary" disabled={busy} onClick={onCancel}>
          Hủy
        </Button>
        <Button disabled={busy} onClick={onConfirm}>
          Xác nhận xóa
        </Button>
      </div>
    </div>
  );
}

function MergeNodesDialog({
  nodes,
  defaultFirstKey,
  busy,
  onConfirm,
  onCancel,
}: {
  nodes: Schema<"Node">[];
  defaultFirstKey: string;
  busy: boolean;
  onConfirm: (body: Schema<"MergeNodesIn">) => void;
  onCancel: () => void;
}) {
  const [firstKey, setFirstKey] = useState(defaultFirstKey);
  const [secondKey, setSecondKey] = useState(() => nodes.find((n) => n.key !== defaultFirstKey)?.key ?? nodes[0]!.key);
  const [mode, setMode] = useState<"FIRST" | "SECOND" | "CUSTOM">("FIRST");
  const [customTitle, setCustomTitle] = useState("");
  const [customChapter, setCustomChapter] = useState("");
  const [customBloom, setCustomBloom] = useState<Schema<"BloomLevel">>("UNDERSTAND");

  const valid = firstKey !== secondKey && (mode !== "CUSTOM" || !!customTitle.trim());

  return (
    <div role="dialog" aria-label="Gộp hai nút" className="space-y-3 rounded-lg border border-line-soft bg-surface p-4 shadow-card">
      <h3 className="text-h3 font-semibold">Gộp hai nút kỹ năng</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="space-y-1 text-body-s font-semibold">
          Nút thứ nhất
          <select className={field} value={firstKey} onChange={(e) => setFirstKey(e.target.value)}>
            {nodes.map((n) => (
              <option key={n.key} value={n.key}>
                {n.code ? `${n.code} – ${n.title}` : n.title}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-body-s font-semibold">
          Nút thứ hai
          <select className={field} value={secondKey} onChange={(e) => setSecondKey(e.target.value)}>
            {nodes.map((n) => (
              <option key={n.key} value={n.key}>
                {n.code ? `${n.code} – ${n.title}` : n.title}
              </option>
            ))}
          </select>
        </label>
      </div>
      <fieldset className="space-y-1 text-body-s">
        <legend className="font-semibold">Thông tin nút sau khi gộp</legend>
        <label className="flex items-center gap-2">
          <input type="radio" name="merge-mode" checked={mode === "FIRST"} onChange={() => setMode("FIRST")} />
          Giữ thông tin nút thứ nhất
        </label>
        <label className="flex items-center gap-2">
          <input type="radio" name="merge-mode" checked={mode === "SECOND"} onChange={() => setMode("SECOND")} />
          Giữ thông tin nút thứ hai
        </label>
        <label className="flex items-center gap-2">
          <input type="radio" name="merge-mode" checked={mode === "CUSTOM"} onChange={() => setMode("CUSTOM")} />
          Tự điền lại
        </label>
      </fieldset>
      {mode === "CUSTOM" && (
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="space-y-1 text-body-s font-semibold">
            Tên nút sau khi gộp
            <input className={field} value={customTitle} onChange={(e) => setCustomTitle(e.target.value)} />
          </label>
          <label className="space-y-1 text-body-s font-semibold">
            Chương
            <input className={field} value={customChapter} onChange={(e) => setCustomChapter(e.target.value)} />
          </label>
          <label className="space-y-1 text-body-s font-semibold">
            Mức Bloom
            <select className={field} value={customBloom} onChange={(e) => setCustomBloom(e.target.value as Schema<"BloomLevel">)}>
              {Object.entries(BLOOM_LABEL).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      <div className="flex gap-2">
        <Button variant="secondary" disabled={busy} onClick={onCancel}>
          Hủy
        </Button>
        <Button
          disabled={busy || !valid}
          onClick={() =>
            onConfirm({
              firstKey,
              secondKey,
              mode,
              ...(mode === "CUSTOM" ? { title: customTitle.trim(), chapterRef: customChapter || null, bloomLevel: customBloom } : {}),
            })
          }
        >
          Xác nhận gộp
        </Button>
      </div>
    </div>
  );
}
