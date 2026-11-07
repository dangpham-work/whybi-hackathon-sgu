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

/** Lỗi kiểm tra trước khi phát hành (422 PUBLISH_CHECK_FAILED, details.errors). */
export function publishErrors(e: unknown): string[] | null {
  if (!(e instanceof ApiError) || e.code !== "PUBLISH_CHECK_FAILED") return null;
  const errs = e.details.errors;
  return Array.isArray(errs) ? errs.map((x) => (typeof x === "string" ? x : JSON.stringify(x))) : [e.message];
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
