/**
 * MyMap mẫu cho test SV-02 / SV-03 (GD-06), dựng theo hợp đồng C2-10 (backend/app/models/schemas/mastery.py – PR C2-10).
 * Cây lấy từ tree_ctdl_gt.json: N1–N4 Đạt, N5 Chưa đạt (thử lại được), N6… Khóa.
 */
import type { Schema } from "../../lib/api";
import tree from "./tree_ctdl_gt.json";

type MyMap = Schema<"MyMap">;
type NodeProgress = Schema<"NodeProgress">;

export const CLASS_ID = "0fcd3055-a08a-5a08-b881-bbab21c660c2";
export const nodeIdOf = (key: string) => `id-${key}`;

const TREE = {
  id: "ver-1",
  classId: CLASS_ID,
  versionNo: 1,
  status: "PUBLISHED",
  nodes: tree.nodes.map((n) => ({ ...n, id: nodeIdOf(n.key) })),
  edges: tree.edges,
} as unknown as Schema<"TreeVersion">;

const base = (key: string, extra: Partial<NodeProgress>): NodeProgress => ({
  nodeId: nodeIdOf(key),
  nodeKey: key,
  state: "LOCKED",
  attempts: 0,
  missingPrerequisites: [],
  canStart: false,
  ...extra,
});

export function myMap(override: Partial<Record<string, Partial<NodeProgress>>> = {}, extra: Partial<MyMap> = {}): MyMap {
  const progress: NodeProgress[] = [
    base("n1_bien_bo_nho", { state: "MASTERED", bestScore: 92, attempts: 1, updatedAt: "2026-09-18T03:00:00Z" }),
    base("n2_mang", { state: "MASTERED", bestScore: 81, attempts: 1, updatedAt: "2026-09-22T03:00:00Z" }),
    base("n3_ham_tham_so", { state: "MASTERED", bestScore: 76, attempts: 2, updatedAt: "2026-09-28T03:00:00Z" }),
    base("n4_de_quy", { state: "MASTERED", bestScore: 74, attempts: 1, updatedAt: "2026-10-05T03:00:00Z" }),
    base("n5_con_tro", { state: "NOT_PASSED", bestScore: 58, attempts: 1, canStart: true, lastSessionId: "s-old" }),
    base("n6_cap_phat_dong", { missingPrerequisites: ["n5_con_tro"] }),
    base("n7_dslk", { missingPrerequisites: ["n6_cap_phat_dong"] }),
    base("n8_ngan_xep_hang_doi", { missingPrerequisites: ["n7_dslk"] }),
    base("n9_cay_nhi_phan", { missingPrerequisites: ["n7_dslk"] }),
    base("n10_bst", { missingPrerequisites: ["n9_cay_nhi_phan"] }),
    base("n11_avl", { missingPrerequisites: ["n10_bst"] }),
  ].map((p) => ({ ...p, ...override[p.nodeKey] }));
  return {
    classId: CLASS_ID,
    studentId: "u-sv",
    tree: TREE,
    progress,
    frontier: ["n5_con_tro"],
    masteredCount: 4,
    totalCount: 11,
    ...extra,
  };
}
