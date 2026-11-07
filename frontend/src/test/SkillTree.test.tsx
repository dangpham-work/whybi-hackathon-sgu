import "./reactflow-setup";
import { fireEvent, render, screen } from "@testing-library/react";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { SkillTree, type TreeEdge, type TreeNode } from "../components/SkillTree";
import { MASTERY, type MasteryState } from "../lib/status";
import { layoutTree, NODE_H } from "../lib/tree-layout";
// Bản chép của seed/tree_ctdl_gt.json (Quyền – KT-02) để build Docker (chỉ có frontend/) vẫn typecheck được.
import seed from "./fixtures/tree_ctdl_gt.json";

// Cây mẫu CTDL&GT: 11 nút, 13 cạnh – đúng kiểu Node/Edge camelCase sinh từ OpenAPI.
const nodes = seed.nodes as unknown as TreeNode[];
const edges = seed.edges as unknown as TreeEdge[];

// Chống lệch: khi chạy trong repo đầy đủ, bản chép phải trùng seed gốc (seed đổi → chép lại vào fixtures/).
const SEED = resolve(__dirname, "../../../seed/tree_ctdl_gt.json");
it.skipIf(!existsSync(SEED))("fixture trùng seed/tree_ctdl_gt.json", () => {
  expect(seed).toEqual(JSON.parse(readFileSync(SEED, "utf-8")));
});

const mastery: Record<string, MasteryState> = {
  n1_bien_bo_nho: "MASTERED",
  n2_mang: "MASTERED",
  n3_ham_tham_so: "MASTERED",
  n4_de_quy: "IN_PROGRESS",
  n5_con_tro: "NOT_PASSED",
  n6_cap_phat_dong: "LOCKED",
  n7_dslk: "LOCKED",
  n8_ngan_xep_hang_doi: "AVAILABLE",
  n9_cay_nhi_phan: "LOCKED",
  n10_bst: "LOCKED",
  n11_avl: "NEEDS_REVERIFY",
};

describe("SkillTree (GD-03)", () => {
  it("vẽ đủ 11 nút và 13 cạnh của cây mẫu", () => {
    const { container } = render(<SkillTree mode="learner" nodes={nodes} edges={edges} mastery={mastery} />);
    expect(container.querySelectorAll(".react-flow__node")).toHaveLength(11);
    expect(container.querySelectorAll(".react-flow__edge")).toHaveLength(13);
    expect(screen.getByText("Con trỏ")).toBeTruthy();
  });

  it("mỗi nút hiện nhãn trạng thái kèm biểu tượng (NFR-12)", () => {
    const { container } = render(<SkillTree mode="learner" nodes={nodes} edges={edges} mastery={mastery} legend={false} />);
    const count = (s: MasteryState) => Object.values(mastery).filter((v) => v === s).length;
    for (const state of Object.keys(MASTERY) as MasteryState[]) {
      expect(screen.queryAllByText(MASTERY[state].label)).toHaveLength(count(state));
    }
    for (const el of container.querySelectorAll(".react-flow__node")) expect(el.querySelector("svg")).toBeTruthy();
  });

  it("nút có nhãn đọc được cho trình đọc màn hình", () => {
    render(<SkillTree mode="learner" nodes={nodes} edges={edges} mastery={mastery} />);
    expect(screen.getByLabelText("N5 Con trỏ – Chưa đạt")).toBeTruthy();
  });

  it("chế độ bản đồ nhiệt tô theo HEAT và đánh dấu điểm nghẽn gốc", () => {
    render(
      <SkillTree
        mode="heatmap"
        nodes={nodes}
        edges={edges}
        heat={{ n5_con_tro: "RED", n1_bien_bo_nho: "GREEN" }}
        rootCauseKey="n5_con_tro"
        legend={false}
      />,
    );
    expect(screen.getByText("< 40%")).toBeTruthy();
    expect(screen.getByText("Đạt ≥ 70%")).toBeTruthy();
    expect(screen.getAllByText("Chưa đủ mẫu")).toHaveLength(9);
    expect(screen.getByText("GỐC")).toBeTruthy();
  });

  it("có chú giải trạng thái bên dưới", () => {
    render(<SkillTree mode="learner" nodes={nodes} edges={edges} mastery={mastery} />);
    expect(screen.getByText("Chú giải")).toBeTruthy();
  });

  it("nhấn nút gọi onNodeClick với đúng nút", () => {
    const onNodeClick = vi.fn();
    render(<SkillTree mode="learner" nodes={nodes} edges={edges} mastery={mastery} onNodeClick={onNodeClick} />);
    fireEvent.click(screen.getByText("Con trỏ"));
    expect(onNodeClick).toHaveBeenCalledWith(expect.objectContaining({ key: "n5_con_tro" }));
  });
});

describe("layoutTree – tự sắp xếp bằng dagre", () => {
  const pos = layoutTree(nodes, edges);

  it("xếp đúng thứ tự tiên quyết: nút tiên quyết luôn nằm trên nút phụ thuộc", () => {
    for (const e of edges) expect(pos.get(e.fromKey)!.y).toBeLessThan(pos.get(e.toKey)!.y);
  });

  it("N1 (không có tiên quyết) ở tầng trên cùng, N11 AVL ở tầng dưới cùng", () => {
    const ys = [...pos.values()].map((p) => p.y);
    expect(pos.get("n1_bien_bo_nho")!.y).toBe(Math.min(...ys));
    expect(pos.get("n11_avl")!.y).toBe(Math.max(...ys));
  });

  it("các nút không chồng lên nhau", () => {
    const ps = [...pos.values()];
    for (let i = 0; i < ps.length; i++)
      for (let j = i + 1; j < ps.length; j++) {
        const overlap = Math.abs(ps[i].x - ps[j].x) < 200 && Math.abs(ps[i].y - ps[j].y) < NODE_H;
        expect(overlap).toBe(false);
      }
  });

  it("dùng vị trí GV đã lưu khi mọi nút đều có positionX/Y", () => {
    const saved = nodes.map((n, i) => ({ ...n, positionX: i * 10, positionY: 500 - i }));
    const p = layoutTree(saved, edges);
    expect(p.get("n1_bien_bo_nho")).toEqual({ x: 0, y: 500 });
  });

  it("LR: nút tiên quyết luôn nằm bên trái", () => {
    const lr = layoutTree(nodes, edges, "LR");
    for (const e of edges) expect(lr.get(e.fromKey)!.x).toBeLessThan(lr.get(e.toKey)!.x);
  });
});
