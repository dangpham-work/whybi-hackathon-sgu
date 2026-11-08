import type { Schema } from "./api";
import { ApiError } from "./api";

export type TreeVersion = Schema<"TreeVersion">;
export type TreeNodeT = Schema<"Node">;
export type Rubric = Schema<"Rubric">;

/** Chỉ sửa được bản nháp / đang sửa (backend trả 409 VERSION_NOT_EDITABLE nếu không). */
export const isEditable = (t: TreeVersion) => t.status === "DRAFT" || t.status === "EDITING";

/** Các nút có rubric chưa duyệt – chặn phát hành theo BR-05. */
export const unapproved = (t: TreeVersion) => t.nodes.filter((n) => !n.rubric?.approved);

/** Dựng câu báo chu trình theo đường đi (FR-SK-07, TC03): "Con trỏ → Hàm → Con trỏ". Trả null nếu không phải lỗi chu trình. */
export function cycleMessage(e: unknown, nodes: TreeNodeT[]): string | null {
  if (!(e instanceof ApiError) || e.code !== "CYCLE_DETECTED") return null;
  const path = Array.isArray(e.details.path) ? (e.details.path as string[]) : [];
  const name = (key: string) => nodes.find((n) => n.key === key)?.title ?? key;
  return path.length ? `Cạnh này tạo chu trình: ${path.map(name).join(" → ")}.` : e.message;
}

export type PublishErrorItem = { text: string; nodeKey?: string };

/** Lỗi kiểm tra trước khi phát hành (422 PUBLISH_CHECK_FAILED, details.errors) kèm nodeKey để bấm chọn nút (#194). */
export function publishErrorItems(e: unknown): PublishErrorItem[] | null {
  if (!(e instanceof ApiError) || e.code !== "PUBLISH_CHECK_FAILED") return null;
  const errs = e.details.errors;
  if (!Array.isArray(errs)) return [{ text: e.message }];
  return errs.map((x) => {
    if (typeof x === "string") return { text: x };
    if (x && typeof x === "object") {
      const obj = x as { message?: unknown; nodeKey?: unknown; code?: unknown };
      const text = typeof obj.message === "string" && obj.message.trim() ? obj.message : typeof obj.code === "string" ? obj.code : e.message;
      const nodeKey = typeof obj.nodeKey === "string" ? obj.nodeKey : undefined;
      return { text, nodeKey };
    }
    return { text: String(x) };
  });
}

/** Lỗi kiểm tra trước khi phát hành dạng mảng chuỗi (#194). */
export function publishErrors(e: unknown): string[] | null {
  return publishErrorItems(e)?.map((x) => x.text) ?? null;
}

/** Các cạnh A → C sẽ được tự nối thêm khi xóa nút X nằm giữa A → X → C (#198). */
export function autoConnectedOnDelete(tree: TreeVersion, nodeKey: string): { fromKey: string; toKey: string }[] {
  const prereqs = tree.edges.filter((e) => e.toKey === nodeKey).map((e) => e.fromKey);
  const succs = tree.edges.filter((e) => e.fromKey === nodeKey).map((e) => e.toKey);
  const existing = new Set(tree.edges.filter((e) => e.fromKey !== nodeKey && e.toKey !== nodeKey).map((e) => `${e.fromKey}->${e.toKey}`));
  const added: { fromKey: string; toKey: string }[] = [];
  for (const fromKey of prereqs) {
    for (const toKey of succs) {
      const sig = `${fromKey}->${toKey}`;
      if (fromKey !== toKey && !existing.has(sig)) {
        existing.add(sig);
        added.push({ fromKey, toKey });
      }
    }
  }
  return added;
}

/** Khóa nút mới, không trùng khóa hiện có. */
export function newNodeKey(nodes: TreeNodeT[]): string {
  let i = nodes.length + 1;
  while (nodes.some((n) => n.key === `n${i}`)) i++;
  return `n${i}`;
}

/** Rubric rỗng cho nút mới. */
export const emptyRubric = (): Rubric => ({
  keyPoints: [],
  optionalPoints: [],
  misconceptions: [],
  scenarios: [],
  targetBloom: "UNDERSTAND",
  passThreshold: 70,
  minChallenges: 3,
  minPassedChallenges: 2,
  sourcePages: [],
  approved: false,
});
