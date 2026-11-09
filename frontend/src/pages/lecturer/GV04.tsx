import { CheckCheck, CircleCheck, Flag, History, Lock, Plus, Sparkles, Trash2, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { AsyncView, ErrorBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { RubricEditor } from "../../components/RubricEditor";
import { VersionHistory } from "../../components/VersionHistory";
import { SkillTree, BLOOM_LABEL } from "../../components/SkillTree";
import { apiCall, ApiError, errorText, type Schema } from "../../lib/api";
import { layoutTree } from "../../lib/tree-layout";
import {
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
  const [cycleEdge, setCycleEdge] = useState<{ fromKey: string; toKey: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: "error" | "ok"; items: PublishErrorItem[] }>();
  const [adding, setAdding] = useState(false);
  const [history, setHistory] = useState(false);
  const [title, setTitle] = useState("");
  const editable = isEditable(tree);
  const selected = tree.nodes.find((n) => n.key === selectedKey);
  const missing = unapproved(tree);
  const noRubric = tree.nodes.filter((n) => !n.rubric);
  const [filling, setFilling] = useState(false);
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

  /** Sinh rubric cho nút chưa có (dựng cây với "chưa sinh rubric"): chạy nền, hỏi lại cây mỗi 5 giây tới khi đủ (tối đa 10 phút). */
  const fillMissing = () =>
    run(async () => {
      // OpenAPI chưa khai báo thân 202 nên kiểu trả về là void – ép về FillRubricsAccepted (như GV03)
      const r = (await apiCall("post", "/classes/{class_id}/tree/rubrics/generate-missing", {
        path: { class_id: classId },
      })) as unknown as Schema<"FillRubricsAccepted">;
      if (r.missing === 0) {
        setMessage({ kind: "ok", items: [{ text: "Mọi nút đã có rubric." }] });
        return;
      }
      setFilling(true);
      setMessage({ kind: "ok", items: [{ text: `Đã xếp hàng sinh rubric cho ${r.missing} nút – rubric sẽ hiện dần, nhớ xem và duyệt.` }] });
    });

  useEffect(() => {
    if (!filling) return;
    const started = Date.now();
    const timer = setInterval(async () => {
      try {
        const fresh = await apiCall("get", "/classes/{class_id}/tree", { path: { class_id: classId }, query: { draft: true } });
        const byKey = new Map(fresh.nodes.map((n) => [n.key, n.rubric]));
        // chỉ điền rubric cho nút local chưa có, không đè thứ GV đang sửa
        setTree((t) => ({ ...t, nodes: t.nodes.map((n) => (!n.rubric && byKey.get(n.key) ? { ...n, rubric: byKey.get(n.key) } : n)) }));
        if (fresh.nodes.every((n) => n.rubric)) {
          setFilling(false);
          setMessage({ kind: "ok", items: [{ text: "AI đã sinh rubric cho mọi nút – hãy xem và duyệt từng nút." }] });
        }
      } catch {
        /* lần hỏi sau thử lại */
      }
      if (Date.now() - started > 10 * 60_000) {
        setFilling(false);
        setMessage({ kind: "error", items: [{ text: "Sinh rubric quá lâu – tải lại trang để xem nút nào còn thiếu, rồi sinh từng nút." }] });
      }
    }, 5000);
    return () => clearInterval(timer);
  }, [filling, classId]);

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

  const removeNode = () => {
    if (!selected?.id || !window.confirm(`Xóa nút "${selected.title}" cùng các cạnh và rubric của nó?`)) return;
    return run(async () => {
      await apiCall("delete", "/nodes/{node_id}", { path: { node_id: selected.id! } });
      setTree((t) => ({
        ...t,
        nodes: t.nodes.filter((n) => n.key !== selected.key),
        edges: t.edges.filter((e) => e.fromKey !== selected.key && e.toKey !== selected.key),
      }));
      setSelectedKey(null);
      setMessage({ kind: "ok", items: [{ text: "Đã xóa nút. Muốn gộp: sửa nội dung nút còn lại cho đủ ý của cả hai." }] });
    });
  };
  const connect = (from: string, to: string) =>
    run(
      async () => {
        const edge = await apiCall("post", "/tree-versions/{version_id}/edges", { path: { version_id: tree.id! }, body: { fromKey: from, toKey: to, source: "LECTURER" } });
        setTree((t) => ({ ...t, edges: [...t.edges, edge] }));
        setCycleEdge(null);
      },
      (e) => {
        if (e instanceof ApiError && e.code === "CYCLE_DETECTED") {
          setCycleEdge({ fromKey: from, toKey: to });
        }
        return [{ text: cycleMessage(e, tree.nodes) ?? errorText(e) }];
      },
    );

  const autoLayout = () =>
    run(async () => {
      const newPos = layoutTree(tree.nodes, tree.edges, "TB");
      const positions = tree.nodes
        .filter((n) => n.id && newPos.has(n.key))
        .map((n) => ({
          nodeId: n.id!,
          x: Math.round(newPos.get(n.key)!.x),
          y: Math.round(newPos.get(n.key)!.y),
        }));
      await apiCall("put", "/tree-versions/{version_id}/positions", {
        path: { version_id: tree.id! },
        body: { positions },
      });
      setTree((t) => ({
        ...t,
        nodes: t.nodes.map((n) => {
          const p = newPos.get(n.key);
          return p ? { ...n, positionX: p.x, positionY: p.y } : n;
        }),
      }));
      setCycleEdge(null);
      setMessage({ kind: "ok", items: [{ text: "Đã tự động sắp xếp lại cây kỹ năng." }] });
    });

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
      setMessage({ kind: "error", items: [{ text: `Không lưu được vị trí nút "${n.title}": ${errorText(e)}` }] }),
    );
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

  const approveAll = () =>
    run(async () => {
      const nodeIds = tree.nodes.filter((n) => n.id && (!n.rubric || !n.rubric.approved)).map((n) => n.id!);
      if (nodeIds.length === 0) return;
      const res = await apiCall("post", "/classes/{class_id}/tree/rubrics/approve", {
        path: { class_id: classId },
        body: { nodeIds },
      });
      const approvedSet = new Set(res.approved);
      setTree((t) => ({
        ...t,
        nodes: t.nodes.map((n) =>
          n.id && approvedSet.has(n.id) ? { ...n, rubric: n.rubric ? { ...n.rubric, approved: true } : n.rubric } : n,
        ),
      }));
      if (res.rejected.length > 0) {
        setMessage({
          kind: "error",
          items: res.rejected.map((r) => {
            const n = tree.nodes.find((x) => x.id === r.nodeId);
            return {
              nodeKey: n?.key,
              text: `Rubric "${n?.title ?? r.nodeId}": ${r.reason}`,
            };
          }),
        });
      } else {
        setMessage({
          kind: "ok",
          items: [{ text: `Đã duyệt ${res.approved.length} rubric. Cây đã sẵn sàng để phát hành!` }],
        });
      }
    });

  return (
    <>
      <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Công cụ sửa cây">
        <Button variant="secondary" disabled={!editable || busy} onClick={() => setAdding((a) => !a)}>
          <Plus aria-hidden size={16} /> Thêm nút
        </Button>
        {/* Không có "Gộp nút": muốn gộp thì xóa một nút, rồi sửa nội dung nút còn lại. */}
        <Button
          variant="secondary"
          disabled={!editable || busy || !selected?.id}
          title={selected ? "Xóa nút đang chọn" : "Chọn một nút trên cây để xóa"}
          onClick={removeNode}
        >
          <Trash2 aria-hidden size={16} /> Xóa nút
        </Button>
        <Button variant="secondary" aria-pressed={history} onClick={() => setHistory((h) => !h)}>
          <History aria-hidden size={16} /> Lịch sử
        </Button>
        <Button variant="secondary" disabled={!editable || busy} title="Tự động sắp xếp các nút phân tầng hợp lý" onClick={autoLayout}>
          <Sparkles aria-hidden size={16} /> Sắp xếp
        </Button>
        {editable && missing.length > 0 && (
          <Button variant="secondary" disabled={busy} onClick={approveAll}>
            <CheckCheck aria-hidden size={16} /> Duyệt tất cả rubric ({missing.length})
          </Button>
        )}
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
              {editable && missing.length > 0 && message.items.some((i) => i.text.includes("chưa duyệt")) && (
                <div className="pt-2">
                  <Button variant="secondary" disabled={busy} onClick={approveAll}>
                    <CheckCheck aria-hidden size={14} /> Duyệt tất cả rubric ({missing.length})
                  </Button>
                </div>
              )}
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

      {editable && noRubric.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-md bg-honey-soft px-3 py-2 text-body-s">
          <span className="flex items-center gap-2 font-semibold text-honey-deep">
            <TriangleAlert aria-hidden size={14} /> {noRubric.length} nút chưa có rubric
          </span>
          <Button variant="secondary" disabled={busy || filling} onClick={fillMissing}>
            {filling ? "Đang sinh rubric…" : "Sinh rubric cho nút còn thiếu"}
          </Button>
          <span className="text-ink-500">Nên bỏ bớt nút không cần trước khi sinh để đỡ tốn.</span>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        <section aria-label="Khung vẽ cây" className="space-y-3 rounded-lg border border-line-soft bg-surface p-4">
          <p className="text-body-s text-ink-500">Kéo từ mép nút để tạo cạnh tiên quyết · thao tác tạo chu trình sẽ bị chặn (BR-01).</p>
          <SkillTree
            mode="edit"
            nodes={tree.nodes}
            edges={tree.edges}
            selectedKey={selectedKey}
            cycleEdge={cycleEdge}
            onClearCycleEdge={() => setCycleEdge(null)}
            height={420}
            onNodeClick={(n) => {
              setCycleEdge(null);
              setSelectedKey(n.key);
            }}
            onNodeMove={editable ? move : undefined}
            onConnect={editable ? connect : undefined}
          />
          <div className="flex flex-wrap items-center justify-between gap-2 text-body-s">
            {missing.length > 0 ? (
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-honey-soft px-3 py-2 text-honey-deep w-full">
                <p className="flex items-center gap-2 font-semibold">
                  <TriangleAlert aria-hidden size={14} /> {missing.length} nút chưa duyệt rubric: {missing.map((n) => n.code ?? n.title).join(", ")} – chưa thể phát hành (BR-05)
                </p>
                {editable && (
                  <Button variant="secondary" disabled={busy} onClick={approveAll}>
                    <CheckCheck aria-hidden size={14} /> Duyệt tất cả rubric ({missing.length})
                  </Button>
                )}
              </div>
            ) : (
              <p className="flex items-center gap-2 font-semibold text-teal">
                <CircleCheck aria-hidden size={14} /> Mọi rubric đã duyệt
              </p>
            )}
            <span className="text-teal ml-auto">{`${tree.nodes.length} nút · ${tree.edges.length} cạnh`}</span>
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
