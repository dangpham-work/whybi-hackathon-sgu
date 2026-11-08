import { Flag, History, Plus, Trash2, TriangleAlert, CircleCheck, Lock } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router";
import { AsyncView, ErrorBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { RubricEditor } from "../../components/RubricEditor";
import { VersionHistory } from "../../components/VersionHistory";
import { SkillTree, BLOOM_LABEL } from "../../components/SkillTree";
import { apiCall, errorText, type Schema } from "../../lib/api";
import { cycleMessage, emptyRubric, isEditable, newNodeKey, publishErrors, unapproved, type Rubric, type TreeVersion } from "../../lib/tree-edit";
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
  const [message, setMessage] = useState<{ kind: "error" | "ok"; lines: string[] }>();
  const [adding, setAdding] = useState(false);
  const [history, setHistory] = useState(false);
  const [title, setTitle] = useState("");
  const editable = isEditable(tree);
  const selected = tree.nodes.find((n) => n.key === selectedKey);
  const missing = unapproved(tree);

  /** Chạy một thao tác ghi: báo lỗi dễ hiểu, không làm mất bản vẽ hiện tại. */
  async function run(action: () => Promise<void>, onError?: (e: unknown) => string[] | null) {
    setBusy(true);
    setMessage(undefined);
    try {
      await action();
    } catch (e) {
      setMessage({ kind: "error", lines: onError?.(e) ?? [errorText(e)] });
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
        body: {
          key: newNodeKey(tree.nodes),
          title: title.trim(),
          bloomLevel: "UNDERSTAND",
          aliases: [],
          rubric: emptyRubric(),
        },
      });
      setTree((t) => ({ ...t, nodes: [...t.nodes, node] }));
      setTitle("");
      setAdding(false);
      setSelectedKey(node.key);
    });

  const connect = (from: string, to: string) =>
    run(
      async () => {
        const edge = await apiCall("post", "/tree-versions/{version_id}/edges", { path: { version_id: tree.id! }, body: { fromKey: from, toKey: to, source: "LECTURER" } });
        setTree((t) => ({ ...t, edges: [...t.edges, edge] }));
      },
      (e) => [cycleMessage(e, tree.nodes) ?? errorText(e)],
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
    void apiCall("patch", "/nodes/{node_id}", { path: { node_id: n.id }, body: { positionX: pos.x, positionY: pos.y } }).catch((e) =>
      setMessage({ kind: "error", lines: [`Không lưu được vị trí nút "${n.title}": ${errorText(e)}`] }),
    );
  };

  const saveBasics = (n: Schema<"Node">) =>
    run(async () => {
      const saved = await apiCall("patch", "/nodes/{node_id}", {
        path: { node_id: n.id! },
        body: { title: n.title, chapterRef: n.chapterRef, bloomLevel: n.bloomLevel },
      });
      patchNode(n.key, (x) => ({ ...x, ...saved, rubric: x.rubric }));
      setMessage({ kind: "ok", lines: ["Đã lưu thông tin nút."] });
    });

  const saveRubric = (n: Schema<"Node">, r: Rubric) =>
    run(async () => {
      const saved = await apiCall("put", "/nodes/{node_id}/rubric", { path: { node_id: n.id! }, body: r });
      patchNode(n.key, (x) => ({ ...x, rubric: saved }));
      setMessage({ kind: "ok", lines: [saved.approved ? "Đã duyệt rubric." : "Đã lưu rubric (chưa duyệt)."] });
    });

  const regenerate = (n: Schema<"Node">) =>
    run(async () => {
      const fresh = await apiCall("post", "/nodes/{node_id}/rubric/regenerate", { path: { node_id: n.id! } });
      patchNode(n.key, (x) => ({ ...x, rubric: fresh }));
      setMessage({ kind: "ok", lines: ["AI đã sinh lại rubric – hãy xem và duyệt."] });
    });

  const publish = () =>
    run(
      async () => {
        const done = await apiCall("post", "/tree-versions/{version_id}/publish", { path: { version_id: tree.id! } });
        setTree(done);
        setMessage({ kind: "ok", lines: [`Đã phát hành phiên bản v${done.versionNo} cho lớp.`] });
      },
      (e) => publishErrors(e) ?? [errorText(e)],
    );

  return (
    <>
      <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Công cụ sửa cây">
        <Button variant="secondary" disabled={!editable || busy} onClick={() => setAdding((a) => !a)}>
          <Plus aria-hidden size={16} /> Thêm nút
        </Button>
        {/* Backend chưa có DELETE /nodes và gộp nút (cần C2) – giữ nút ở trạng thái khóa, không giả lập */}
        <Button variant="secondary" disabled title="Chờ API xóa nút (C2)">
          <Trash2 aria-hidden size={16} /> Xóa nút
        </Button>
        <Button variant="secondary" disabled title="Chờ API gộp nút (C2)">
          Gộp nút
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
      {message && (message.kind === "error" ? <ErrorBox text={message.lines.join(" ")} /> : <p role="status" className="flex items-center gap-2 text-body-m text-teal"><CircleCheck aria-hidden size={16} />{message.lines.join(" ")}</p>)}
      {message?.kind === "error" && message.lines.length > 1 && (
        <ul className="list-disc pl-6 text-body-s">
          {message.lines.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      )}

      {history && (
        <VersionHistory
          classId={classId}
          nodeTitle={(key) => tree.nodes.find((n) => n.key === key)?.title ?? key}
          onRestored={(draft) => {
            setTree(draft);
            setSelectedKey(null);
            setHistory(false);
            setMessage({ kind: "ok", lines: [`Đã khôi phục thành bản nháp v${draft.versionNo} – duyệt lại rubric rồi phát hành.`] });
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
