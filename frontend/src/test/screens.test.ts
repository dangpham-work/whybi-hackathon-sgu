import { SCREENS } from "../screens";

describe("danh mục màn hình", () => {
  it("đủ 18 màn của Bảng 5.12", () => {
    const codes = SCREENS.map((s) => s.code).filter((c) => /^(GV|SV)-/.test(c));
    expect(codes).toHaveLength(18);
  });
  it("mã và đường dẫn không trùng", () => {
    expect(new Set(SCREENS.map((s) => s.code)).size).toBe(SCREENS.length);
    expect(new Set(SCREENS.map((s) => s.path)).size).toBe(SCREENS.length);
  });
});
