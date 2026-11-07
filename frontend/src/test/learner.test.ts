import { describe, expect, it } from "vitest";
import { learnerView, nodeDetail, nextToLearn, prerequisitesOf } from "../lib/learner";
import { myMap } from "./fixtures/my-map";

describe("lib/learner – dữ liệu SV-02 / SV-03 từ MyMap (GD-06)", () => {
  it("sắp nút theo thứ tự tiên quyết: tiên quyết luôn đứng trước", () => {
    const view = learnerView(myMap());
    const order = view.items.map((i) => i.node.code);
    expect(order).toHaveLength(11);
    for (const e of myMap().tree.edges) {
      const from = view.items.findIndex((i) => i.node.key === e.fromKey);
      const to = view.items.findIndex((i) => i.node.key === e.toKey);
      expect(from).toBeLessThan(to);
    }
    expect(order[0]).toBe("N1");
  });

  it("nút thiếu trong progress coi là Khóa (không đoán trạng thái)", () => {
    const m = myMap();
    m.progress = m.progress.filter((p) => p.nodeKey !== "n11_avl");
    const item = learnerView(m).items.find((i) => i.node.key === "n11_avl")!;
    expect(item.progress.state).toBe("LOCKED");
    expect(item.progress.canStart).toBe(false);
  });

  it("dòng phụ luôn có chữ trạng thái kèm điểm / lượt / tiên quyết còn thiếu", () => {
    const view = learnerView(myMap());
    const detail = (key: string) => nodeDetail(view.items.find((i) => i.node.key === key)!.progress, view.byKey);
    expect(detail("n1_bien_bo_nho")).toMatch(/^Đạt 92\/100/);
    expect(detail("n5_con_tro")).toBe("Chưa đạt · cao nhất 58/100 · 1 lượt");
    expect(detail("n6_cap_phat_dong")).toBe("Khóa · mở khi bạn Đạt N5");
  });

  it("chưa thử thì ghi 'chưa thử'; còn chờ BR-11 thì ghi giờ thử lại", () => {
    const later = new Date(Date.now() + 5 * 60_000).toISOString();
    const view = learnerView(
      myMap({
        n5_con_tro: { retryAt: later, canStart: false },
        n6_cap_phat_dong: { state: "AVAILABLE", missingPrerequisites: [], canStart: true },
      }),
    );
    const p = (key: string) => view.items.find((i) => i.node.key === key)!.progress;
    expect(nodeDetail(p("n6_cap_phat_dong"), view.byKey)).toBe("Sẵn sàng · chưa thử");
    expect(nodeDetail(p("n5_con_tro"), view.byKey)).toMatch(/Chưa đạt · cao nhất 58\/100 · 1 lượt · thử lại lúc \d{2}:\d{2}/);
  });

  it("nút nên học tiếp: ưu tiên frontier và canStart", () => {
    expect(nextToLearn(learnerView(myMap()))?.node.code).toBe("N5");
    expect(nextToLearn(learnerView(myMap({ n5_con_tro: { canStart: false } })))).toBeNull();
  });

  it("tiên quyết của một nút lấy từ cạnh của cây, kèm trạng thái", () => {
    const view = learnerView(myMap());
    const pre = prerequisitesOf("n5_con_tro", view);
    expect(pre.map((x) => [x.node.code, x.progress.state])).toEqual([
      ["N1", "MASTERED"],
      ["N3", "MASTERED"],
    ]);
  });
});
