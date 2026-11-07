import { createTypingMeter } from "../lib/typing-meter";

/** Đồng hồ giả để đo tốc độ gõ không phụ thuộc máy chạy test. */
function clock(start = 0) {
  let t = start;
  return { now: () => t, tick: (ms: number) => (t += ms) };
}

describe("TypingMeter – sự kiện dán và tốc độ gõ (FR-TB-04)", () => {
  it("chưa nhập gì thì pasteRatio = 0, typingCps = 0", () => {
    const m = createTypingMeter(clock().now);
    expect(m.snapshot()).toEqual({ pasteRatio: 0, typingCps: 0 });
  });

  it("gõ tay 10 ký tự trong 2 giây → 5 ký tự/giây, không dán", () => {
    const c = clock();
    const m = createTypingMeter(c.now);
    let text = "";
    for (let i = 0; i < 10; i++) {
      const next = text + "a";
      m.change(text, next);
      text = next;
      if (i < 9) c.tick(222); // 9 khoảng ≈ 2 s
    }
    const s = m.snapshot();
    expect(s.pasteRatio).toBe(0);
    expect(s.typingCps).toBeCloseTo(5, 0);
  });

  it("dán 30 ký tự rồi gõ 10 ký tự → pasteRatio = 0.75; ký tự dán không tính vào tốc độ gõ", () => {
    const c = clock();
    const m = createTypingMeter(c.now);
    const pasted = "x".repeat(30);
    m.paste(pasted.length);
    m.change("", pasted);
    let text = pasted;
    for (let i = 0; i < 10; i++) {
      c.tick(100);
      const next = text + "b";
      m.change(text, next);
      text = next;
    }
    const s = m.snapshot();
    expect(s.pasteRatio).toBeCloseTo(0.75, 5);
    expect(s.typingCps).toBeGreaterThan(5);
  });

  it("chỉ dán (không gõ phím nào) → pasteRatio = 1, typingCps = 0", () => {
    const m = createTypingMeter(clock().now);
    m.paste(50);
    m.change("", "y".repeat(50));
    expect(m.snapshot()).toEqual({ pasteRatio: 1, typingCps: 0 });
  });

  it("khoảng nghỉ dài không kéo tốc độ gõ xuống (chỉ tính thời gian gõ thật)", () => {
    const c = clock();
    const m = createTypingMeter(c.now);
    m.change("", "a");
    c.tick(200);
    m.change("a", "ab");
    c.tick(60_000); // nghỉ 1 phút để suy nghĩ
    m.change("ab", "abc");
    c.tick(200);
    m.change("abc", "abcd");
    expect(m.snapshot().typingCps).toBeGreaterThan(1);
  });

  it("xóa bớt không làm âm số ký tự gõ; reset() đưa về 0", () => {
    const m = createTypingMeter(clock().now);
    m.change("", "abc");
    m.change("abc", "a");
    expect(m.snapshot().pasteRatio).toBe(0);
    m.reset();
    expect(m.snapshot()).toEqual({ pasteRatio: 0, typingCps: 0 });
  });

  it("IME / đọc chính tả chèn nhiều ký tự vẫn cho số hữu hạn, không tính là dán", () => {
    const c = clock();
    const m = createTypingMeter(c.now);
    m.change("", "xin chào");
    expect(m.snapshot()).toEqual({ pasteRatio: 0, typingCps: 0 });
    c.tick(1_000);
    m.change("xin chào", "xin chào bạn");
    expect(m.snapshot()).toEqual({ pasteRatio: 0, typingCps: 12 });
    // IME thay chữ mà độ dài không đổi, hoặc nhập thêm trong cùng một nhịp đồng hồ.
    m.change("xin chào bạn", "xin chào bàn");
    m.change("xin chào bàn", "xin chào bàn!");
    expect(Number.isFinite(m.snapshot().typingCps)).toBe(true);
  });

  it("xóa chữ đã dán vẫn đo lịch sử nhập, pasteRatio không vượt [0,1]", () => {
    const m = createTypingMeter(clock().now);
    m.paste(30);
    m.change("", "x".repeat(30));
    m.change("x".repeat(30), "x");
    expect(m.snapshot()).toEqual({ pasteRatio: 1, typingCps: 0 });
    m.change("x", "");
    m.change("", "a".repeat(10));
    expect(m.snapshot().pasteRatio).toBe(0.75);
  });
});
