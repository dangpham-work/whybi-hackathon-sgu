import { render, screen } from "@testing-library/react";
import { StatusBadge, StatusLegend } from "../components/StatusBadge";
import { HEAT, MASTERY, ROOT_CAUSE } from "../lib/status";

describe("trạng thái luôn có biểu tượng + chữ (NFR-12, GD-01)", () => {
  it("mọi trạng thái MASTERY / HEAT / ROOT_CAUSE có icon và nhãn", () => {
    for (const look of [...Object.values(MASTERY), ...Object.values(HEAT), ROOT_CAUSE]) {
      expect(look.icon).toBeTruthy();
      expect(look.label.trim().length).toBeGreaterThan(0);
    }
  });

  it("đủ 6 trạng thái thành thạo và 4 màu bản đồ nhiệt, nhãn và biểu tượng không trùng", () => {
    expect(Object.keys(MASTERY)).toHaveLength(6);
    expect(Object.keys(HEAT)).toHaveLength(4);
    expect(new Set(Object.values(MASTERY).map((l) => l.label)).size).toBe(6);
    expect(new Set(Object.values(MASTERY).map((l) => l.icon)).size).toBe(6);
  });

  it("huy hiệu vẽ ra cả biểu tượng (svg) lẫn chữ", () => {
    const { container } = render(<StatusBadge kind="mastery" value="NOT_PASSED" />);
    expect(screen.getByText("Chưa đạt")).toBeTruthy();
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("chú giải liệt kê mọi trạng thái, mỗi mục có biểu tượng", () => {
    const { container } = render(<StatusLegend kind="mastery" />);
    for (const look of Object.values(MASTERY)) expect(screen.getByText(look.label)).toBeTruthy();
    expect(container.querySelectorAll("svg")).toHaveLength(6);
  });

  it("chú giải bản đồ nhiệt có cả điểm nghẽn gốc", () => {
    render(<StatusLegend kind="heat" />);
    expect(screen.getByText("Điểm nghẽn gốc")).toBeTruthy();
    for (const look of Object.values(HEAT)) expect(screen.getByText(look.label)).toBeTruthy();
  });
});
