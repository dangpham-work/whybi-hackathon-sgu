import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { setToken } from "../lib/api";
import { auth } from "../lib/auth";
import { routes } from "../router";
import { err, mockApi, ok } from "./mock-api";

// Giả kênh WebSocket: test tự đẩy sự kiện job.progress
let push: (e: { channel: string; event: string; payload: unknown }) => void = () => {};
let channel: string | null = null;
vi.mock("../lib/ws", async (orig) => ({
  ...(await orig<typeof import("../lib/ws")>()),
  useChannel: (ch: string | null, h: typeof push) => {
    channel = ch;
    push = h;
    return "open";
  },
}));

const CTDL = { id: "c1", name: "CTDL&GT – Nhóm 02", semester: "HK1 2026–2027", joinCode: "K7M2PQ4A", studentCount: 42, treeStatus: "PUBLISHED" };
const OS = { id: "c2", name: "Hệ điều hành", semester: "HK1 2026–2027", joinCode: "ABCD1234", studentCount: 28, treeStatus: null };
const me = { "GET /me": ok({ id: "u", fullName: "Nguyễn Văn Bình", email: "b@x.vn", role: "LECTURER" }) };

function open(url: string) {
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [url] })} />);
}
beforeEach(() => {
  auth.reset();
  setToken("acc-1");
});
afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

describe("GV-01 Danh sách lớp (GD-05)", () => {
  it("liệt kê lớp, tổng hợp số liệu và gợi ý việc tiếp theo theo trạng thái cây", async () => {
    mockApi({ ...me, "GET /classes": ok([CTDL, OS]) });
    open("/gv/classes");
    const list = await screen.findByRole("list", { name: "Lớp học phần" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("70")).toBeTruthy(); // 42 + 28 sinh viên
    expect(within(list).getByRole("link", { name: /Bản đồ nhiệt/ }).getAttribute("href")).toBe("/gv/classes/c1/heatmap");
    expect(within(list).getByRole("link", { name: /Tải giáo trình/ }).getAttribute("href")).toBe("/gv/classes/c2/syllabus");
    expect(within(list).getByRole("button", { name: "Chép mã tham gia K7M2PQ4A" })).toBeTruthy();
  });
});

describe("GV-02 Tổng quan lớp (GD-05)", () => {
  it("hiện thông tin lớp và phiên bản cây", async () => {
    mockApi({
      ...me,
      "GET /classes": ok([CTDL]),
      "GET /classes/c1/tree": ok({ versionNo: 2, status: "PUBLISHED", nodes: [{}, {}, {}], edges: [{}, {}] }),
    });
    open("/gv/classes/c1");
    expect(await screen.findByRole("heading", { name: "CTDL&GT – Nhóm 02" })).toBeTruthy();
    expect(await screen.findByText("v2")).toBeTruthy();
    expect(screen.getByText("Đã phát hành")).toBeTruthy();
  });

  it("lớp chưa có cây (404) thì mời tải giáo trình", async () => {
    mockApi({ ...me, "GET /classes": ok([OS]), "GET /classes/c2/tree": err(404, "TREE_NOT_FOUND") });
    open("/gv/classes/c2");
    expect(await screen.findByRole("link", { name: /Tải giáo trình/ })).toBeTruthy();
  });
});

describe("GV-03 Tải giáo trình và tiến độ (GD-05)", () => {
  const pick = async (f: File) => fireEvent.change(await screen.findByLabelText("Chọn tệp giáo trình"), { target: { files: [f] } });

  it("tệp sai đuôi bị chặn ngay, không gọi API", async () => {
    const m = mockApi({ ...me });
    open("/gv/classes/c1/syllabus");
    await pick(new File(["x"], "virus.exe"));
    expect(await screen.findByText(/chỉ nhận PDF hoặc DOCX/)).toBeTruthy();
    expect((screen.getByRole("button", { name: /Tải lên/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(m.called("POST /classes/c1/syllabi")).toHaveLength(0);
  });

  it("tải lên rồi thanh tiến độ cập nhật trực tiếp theo job.progress", async () => {
    mockApi({ ...me, "POST /classes/c1/syllabi": ok({ jobId: "job-9", documentId: "d1" }, 202) });
    open("/gv/classes/c1/syllabus");
    await pick(new File(["%PDF"], "gt.pdf", { type: "application/pdf" }));
    fireEvent.click(screen.getByRole("button", { name: /Tải lên/ }));
    await waitFor(() => expect(channel).toBe("job:job-9"));

    act(() => push({ channel: "job:job-9", event: "job.progress", payload: { percent: 40, step: "EXTRACTING" } }));
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("40");
    expect(screen.getByText("Trích văn bản theo trang")).toBeTruthy();

    // DONE đầu tiên chỉ là bóc chữ xong: cây chưa dựng nên chưa được mời mở trình sửa cây
    act(() => push({ channel: "job:job-9", event: "job.progress", payload: { percent: 100, step: "DONE" } }));
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("100");
    expect(screen.queryByRole("link", { name: /Mở trình sửa cây/ })).toBeNull();

    act(() => push({ channel: "job:job-9", event: "job.progress", payload: { percent: 30, step: "CONCEPTS" } }));
    expect(screen.getByText("Trích khái niệm")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Mở trình sửa cây/ })).toBeNull();

    act(() => push({ channel: "job:job-9", event: "job.progress", payload: { percent: 100, step: "DONE" } }));
    act(() => push({ channel: "job:job-9", event: "tree.generated", payload: { versionId: "v1" } }));
    expect(screen.getByRole("link", { name: /Mở trình sửa cây/ })).toBeTruthy();
  });

  it("bấm Hủy khi đang dựng cây thì gọi API hủy giáo trình", async () => {
    const m = mockApi({
      ...me,
      "POST /classes/c1/syllabi": ok({ jobId: "job-9", documentId: "d1" }, 202),
      "POST /classes/c1/syllabi/d1/cancel": ok({ documentId: "d1", status: "CANCELLED" }),
    });
    open("/gv/classes/c1/syllabus");
    await pick(new File(["%PDF"], "gt.pdf", { type: "application/pdf" }));
    fireEvent.click(screen.getByRole("button", { name: /Tải lên/ }));
    await waitFor(() => expect(channel).toBe("job:job-9"));
    act(() => push({ channel: "job:job-9", event: "job.progress", payload: { percent: 30, step: "CONCEPTS" } }));

    fireEvent.click(screen.getByRole("button", { name: /Hủy/ }));
    await waitFor(() => expect(m.called("POST /classes/c1/syllabi/d1/cancel")).toHaveLength(1));
    act(() => push({ channel: "job:job-9", event: "job.progress", payload: { percent: 0, step: "CANCELLED" } }));
    expect(screen.getByText("Đã hủy")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Hủy/ })).toBeNull();
  });

  it("máy chủ báo INVALID_FILE thì hiện câu dễ hiểu", async () => {
    mockApi({ ...me, "POST /classes/c1/syllabi": err(422, "INVALID_FILE") });
    open("/gv/classes/c1/syllabus");
    await pick(new File(["x"], "gt.pdf"));
    fireEvent.click(screen.getByRole("button", { name: /Tải lên/ }));
    expect(await screen.findByText(/Tệp không hợp lệ/)).toBeTruthy();
  });
});
