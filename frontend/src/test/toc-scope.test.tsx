import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { setToken } from "../lib/api";
import { auth } from "../lib/auth";
import { defaultSelected, mergeRanges, parsePageRanges, rangesFromChapters } from "../lib/syllabus-scope";
import { routes } from "../router";
import { mockApi, ok } from "./mock-api";

let push: (e: { channel: string; event: string; payload: unknown }) => void = () => {};
vi.mock("../lib/ws", async (orig) => ({
  ...(await orig<typeof import("../lib/ws")>()),
  useChannel: (_ch: string | null, h: typeof push) => {
    push = h;
    return "open";
  },
}));

const me = { "GET /me": ok({ id: "u", fullName: "Nguyễn Văn Bình", email: "b@x.vn", role: "LECTURER" }) };
const chapter = (index: number, from: number, to: number) => ({ index, title: `Chương ${index}`, startPage: from, endPage: to, pages: to - from + 1, chars: 20000 });
const REPORT = {
  documentId: "d1",
  source: "toc_pages",
  totalPages: 120,
  totalChars: 300000,
  offset: 2,
  tocPages: [2],
  level: "WARN",
  estNodes: 84,
  estCalls: 180,
  charsPerChunk: 12000,
  nodesPerChunk: { SUMMARY: 3, STANDARD: 5, DETAILED: 7 },
  detailCaps: { SUMMARY: 4, STANDARD: 8, DETAILED: 12 },
  chapters: [chapter(1, 3, 10), chapter(2, 11, 18), chapter(3, 19, 26), chapter(4, 40, 50)],
  advice: { message: "Nên chọn chương trọng tâm để tiết kiệm chi phí.", keep: [1, 2], skip: [{ index: 4, reason: "bài tập ôn" }], suggestSplit: false },
  aiWritten: true,
  gated: true,
};

describe("khoanh vùng giáo trình (hàm thuần)", () => {
  it("gộp khoảng liền nhau và chồng nhau", () => {
    expect(mergeRanges([[11, 18], [3, 10], [20, 25], [24, 30]])).toEqual([[3, 18], [20, 30]]);
  });
  it("đọc khoảng trang gõ tay, báo lỗi khi sai", () => {
    expect(parsePageRanges("10-45, 60", 120).ranges).toEqual([[10, 45], [60, 60]]);
    expect(parsePageRanges("", 120)).toEqual({ ranges: [] });
    expect(parsePageRanges("50-130", 120).error).toMatch(/ngoài trang 1–120/);
    expect(parsePageRanges("abc", 120).error).toMatch(/không đúng dạng/);
  });
  it("mặc định theo AI: ưu tiên chương nên giữ, không có thì bỏ chương nên bỏ", () => {
    expect([...defaultSelected(REPORT)]).toEqual([1, 2]);
    const noKeep = { ...REPORT, advice: { ...REPORT.advice, keep: [] } };
    expect([...defaultSelected(noKeep)].sort()).toEqual([1, 2, 3]);
    expect(rangesFromChapters(REPORT.chapters, new Set([1, 4]))).toEqual([[3, 10], [40, 50]]);
  });
});

describe("GV-03 cảnh báo cỡ giáo trình", () => {
  beforeEach(() => {
    auth.reset();
    setToken("acc-1");
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    setToken(null);
  });

  async function upload(toc: unknown) {
    const m = mockApi({
      ...me,
      "POST /classes/c1/syllabi": ok({ jobId: "d1", documentId: "d1" }, 202),
      "GET /classes/c1/syllabi/d1/toc": ok(toc),
      "POST /classes/c1/syllabi/d1/build-tree": ok({ jobId: "d1", documentId: "d1" }, 202),
    });
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/gv/classes/c1/syllabus"] })} />);
    fireEvent.change(await screen.findByLabelText("Chọn tệp giáo trình"), { target: { files: [new File(["%PDF"], "gt.pdf", { type: "application/pdf" })] } });
    fireEvent.click(screen.getByRole("button", { name: /Tải lên/ }));
    await waitFor(() => expect(m.called("POST /classes/c1/syllabi")).toHaveLength(1));
    act(() => push({ channel: "job:d1", event: "syllabus.toc_ready", payload: { documentId: "d1", level: "WARN", gated: true } }));
    return m;
  }
  const build = (m: ReturnType<typeof mockApi>) => m.called("POST /classes/c1/syllabi/d1/build-tree");

  it("hiện lời khuyên AI, tick sẵn chương nên giữ, chọn thêm rồi gửi khoảng trang đã gộp", async () => {
    const m = await upload(REPORT);
    act(() => push({ channel: "job:d1", event: "job.progress", payload: { percent: 100, step: "AWAITING_SELECTION" } }));
    expect(await screen.findByText(/Nên chọn chương trọng tâm/)).toBeTruthy();
    expect(screen.getByText(/Đang chờ thầy\/cô chọn phần cần dựng cây/)).toBeTruthy();
    expect((screen.getByRole("button", { name: /Tải lên/ }) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByText("Lời khuyên do AI viết từ mục lục đã trích.")).toBeTruthy();
    expect(screen.getByText(/Nên bỏ: bài tập ôn/)).toBeTruthy();

    const box = (n: number) => screen.getByRole("checkbox", { name: new RegExp(`^Chương ${n}`) }) as HTMLInputElement;
    expect([box(1).checked, box(2).checked, box(3).checked, box(4).checked]).toEqual([true, true, false, false]);
    fireEvent.click(box(3));
    expect(screen.getByText("Đã chọn 24 / 120 trang · dự kiến ~30 nút, ~36 lượt gọi AI")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Dựng cây từ phần đã chọn" }));

    await waitFor(() => expect(build(m)).toHaveLength(1));
    expect(build(m)[0].body).toEqual({ ranges: [[3, 26]], detail: "STANDARD", lazyRubric: true });
    expect(await screen.findByText(/Đang dựng cây theo lựa chọn/)).toBeTruthy();
    expect(screen.getByText("Trích khái niệm")).toBeTruthy();
  });

  it("không có mục lục: nhập khoảng trang, nhập sai thì chặn nút", async () => {
    const m = await upload({
      ...REPORT,
      source: "none",
      chapters: [],
      offset: null,
      tocPages: [],
      advice: { message: "Không tìm thấy mục lục.", keep: [], skip: [], suggestSplit: true },
      aiWritten: false,
    });
    const input = (await screen.findByLabelText("Khoảng trang cần dựng cây")) as HTMLInputElement;
    const btn = screen.getByRole("button", { name: "Dựng cây từ phần đã chọn" }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    fireEvent.change(input, { target: { value: "50-130" } });
    expect(await screen.findByText(/ngoài trang 1–120/)).toBeTruthy();
    expect(btn.disabled).toBe(true);
    fireEvent.change(input, { target: { value: "10-45, 60-80" } });
    expect(btn.disabled).toBe(false);
    fireEvent.click(btn);
    await waitFor(() => expect(build(m)).toHaveLength(1));
    expect(build(m)[0].body).toEqual({ ranges: [[10, 45], [60, 80]], detail: "STANDARD", lazyRubric: true });
  });

  it("nút 'toàn bộ' gửi danh sách rỗng", async () => {
    const m = await upload(REPORT);
    fireEvent.click(await screen.findByRole("button", { name: "Dựng từ toàn bộ giáo trình" }));
    await waitFor(() => expect(build(m)).toHaveLength(1));
    expect(build(m)[0].body).toEqual({ ranges: [], detail: "STANDARD", lazyRubric: true });
  });

  it("cổng tắt (gated=false): chỉ hiện lời khuyên, không có nút dựng", async () => {
    await upload({ ...REPORT, gated: false });
    expect(await screen.findByText(/Nên chọn chương trọng tâm/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Dựng cây từ phần đã chọn" })).toBeNull();
    expect(screen.getByText(/Đang dựng cây theo lựa chọn/)).toBeTruthy();
  });

  it("giáo trình cỡ vừa (level OK) không hiện bảng cảnh báo", async () => {
    const m = await upload({ ...REPORT, level: "OK", gated: false });
    await waitFor(() => expect(m.called("GET /classes/c1/syllabi/d1/toc")).toHaveLength(1));
    expect(screen.queryByLabelText("Cảnh báo cỡ giáo trình")).toBeNull();
  });

  it("đổi mức chi tiết và bật lại sinh rubric thì ước tính đổi theo, và gửi đúng lựa chọn", async () => {
    const m = await upload(REPORT);
    fireEvent.click(await screen.findByRole("checkbox", { name: /^Chương 3/ }));
    fireEvent.click(screen.getByRole("radio", { name: /Tóm lược/ }));
    expect(screen.getByText("Đã chọn 24 / 120 trang · dự kiến ~18 nút, ~24 lượt gọi AI")).toBeTruthy();
    fireEvent.click(screen.getByRole("checkbox", { name: /Chưa sinh rubric lúc dựng cây/ })); // tắt hoãn ⇒ sinh rubric ngay
    expect(screen.getByText("Đã chọn 24 / 120 trang · dự kiến ~18 nút, ~42 lượt gọi AI")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Dựng cây từ phần đã chọn" }));
    await waitFor(() => expect(build(m)).toHaveLength(1));
    expect(build(m)[0].body).toEqual({ ranges: [[3, 26]], detail: "SUMMARY", lazyRubric: false });
  });

  it("tải lại trang vẫn khôi phục hộp cảnh báo đang chờ chọn (báo cáo lưu ở backend)", async () => {
    mockApi({ ...me, "GET /classes/c1/syllabi/latest/toc": ok(REPORT) });
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/gv/classes/c1/syllabus"] })} />);
    expect(await screen.findByText(/Nên chọn chương trọng tâm/)).toBeTruthy();
    expect(screen.getByText(/Đang chờ thầy\/cô chọn phần cần dựng cây/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Dựng cây từ phần đã chọn" })).toBeTruthy();
  });

  it("tải lại trang nhưng báo cáo đã dựng xong (gated=false) thì không hiện gì", async () => {
    const m = mockApi({ ...me, "GET /classes/c1/syllabi/latest/toc": ok({ ...REPORT, gated: false }) });
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/gv/classes/c1/syllabus"] })} />);
    await waitFor(() => expect(m.called("GET /classes/c1/syllabi/latest/toc")).toHaveLength(1));
    expect(screen.queryByLabelText("Cảnh báo cỡ giáo trình")).toBeNull();
  });
});
