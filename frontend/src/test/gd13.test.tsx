import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { setToken } from "../lib/api";
import { auth } from "../lib/auth";
import { routes } from "../router";
import { err, mockApi, ok } from "./mock-api";

const RESULT = {
  sessionId: "s1",
  studentId: "st1",
  nodeId: "i5",
  classId: "c1",
  state: "NOT_PASSED",
  verdict: "FAILED",
  totalScore: 58,
  passThreshold: 70,
  criteria: [
    { code: "CORRECTNESS", weight: 0.25, score: 18, max: 25, rationale: "Định nghĩa đúng nhưng chưa đủ sâu" },
    { code: "COVERAGE", weight: 0.25, score: 14, max: 25 },
    { code: "ESSENCE", weight: 0.2, score: 10, max: 20 },
    { code: "ROBUSTNESS", weight: 0.2, score: 10, max: 20 },
    { code: "CLARITY", weight: 0.1, score: 6, max: 10 },
  ],
  strengths: [],
  reviewHints: [],
  sourcePages: [],
  unlockedNodes: [],
  flags: ["PASTE_SUSPECTED"],
  isPeerFollowup: false,
  detectedMisconceptions: ["Con trỏ chứa giá trị của biến"],
};
const PROFILE = {
  classId: "c1",
  studentId: "st1",
  fullName: "Trần Bảo Châu",
  studentCode: "3121001",
  masteredCount: 4,
  totalCount: 7,
  progress: [
    { nodeId: "i1", nodeKey: "n1", state: "MASTERED", bestScore: 92, attempts: 1 },
    { nodeId: "i5", nodeKey: "n5", state: "NOT_PASSED", bestScore: 58, attempts: 1 },
  ],
  sessions: [
    {
      sessionId: "s1",
      nodeId: "i5",
      nodeKey: "n5",
      nodeTitle: "Con trỏ",
      attemptNo: 1,
      status: "COMPLETED",
      startedAt: "2026-10-13T07:20:00Z",
      result: RESULT,
      turns: [
        { turnNo: 1, speaker: "TUTEE", turnType: "OPENING", content: "Mình chưa biết con trỏ là gì cả.", inputMode: "TEXT", audioUrl: null, createdAt: "" },
        { turnNo: 2, speaker: "STUDENT", turnType: "EXPLANATION", content: "Con trỏ lưu địa chỉ của một ô nhớ.", inputMode: "VOICE", audioUrl: "/api/v1/turns/t2/audio", createdAt: "" },
        { turnNo: 3, speaker: "TUTEE", turnType: "QUESTION", content: "Nếu hai con trỏ cùng trỏ vào một ô nhớ?", inputMode: "TEXT", audioUrl: null, createdAt: "" },
      ],
    },
  ],
};
const TREE = {
  id: "v1",
  versionNo: 1,
  status: "PUBLISHED",
  nodes: [
    { id: "i1", key: "n1", code: "N1", title: "Biến & bộ nhớ", bloomLevel: "REMEMBER" },
    { id: "i5", key: "n5", code: "N5", title: "Con trỏ", bloomLevel: "UNDERSTAND" },
  ],
  edges: [],
};
const base = {
  "GET /me": ok({ id: "u", fullName: "GV", email: "g@x.vn", role: "LECTURER" }),
  "GET /classes/c1/students/st1/profile": ok(PROFILE),
  "GET /classes/c1/tree": ok(TREE),
};
const open = (url: string) => render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [url] })} />);
beforeEach(() => {
  auth.reset();
  setToken("acc-1");
  URL.createObjectURL = vi.fn(() => "blob:audio");
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

describe("GV-07 Hồ sơ năng lực SV (GD-13)", () => {
  it("hiện tiến độ, điểm trung bình, trạng thái từng nút kèm tên nút và quan niệm sai", async () => {
    mockApi(base);
    open("/gv/classes/c1/students/st1");
    expect(await screen.findByRole("heading", { name: "Trần Bảo Châu" })).toBeTruthy();
    expect(screen.getByText("4/7")).toBeTruthy();
    expect(screen.getByText("Điểm trung bình").closest("div")?.textContent).toContain("58"); // phiên đã chấm duy nhất
    const table = await screen.findByRole("table");
    expect(await within(table).findByText("Con trỏ")).toBeTruthy();
    expect(within(table).getByText("Chưa đạt")).toBeTruthy();
    expect(screen.getByText(/Con trỏ chứa giá trị của biến/)).toBeTruthy();
  });

  it("lịch sử phiên dẫn tới GV-08 kèm lớp và SV", async () => {
    mockApi(base);
    open("/gv/classes/c1/students/st1");
    const link = await screen.findByRole("link", { name: /Con trỏ/ });
    expect(link.getAttribute("href")).toBe("/gv/sessions/s1?classId=c1&studentId=st1");
  });
});

describe("GV-08 Transcript và ghi âm (GD-13)", () => {
  const url = "/gv/sessions/s1?classId=c1&studentId=st1";

  it("hiện transcript đúng người nói, 5 tiêu chí và cờ vi phạm", async () => {
    mockApi(base);
    open(url);
    expect(await screen.findByText("Nếu hai con trỏ cùng trỏ vào một ô nhớ?")).toBeTruthy();
    expect(screen.getByText("Con trỏ lưu địa chỉ của một ô nhớ.")).toBeTruthy();
    expect(screen.getAllByRole("progressbar")).toHaveLength(5);
    expect(screen.getByText("Dán văn bản dài bất thường")).toBeTruthy();
    expect(screen.getByText("1 cảnh báo")).toBeTruthy();
  });

  it("nghe ghi âm: tải bằng token rồi phát", async () => {
    mockApi(base);
    const fetchAudio = vi.fn(async () => new Response(new Blob(["x"]), { status: 200 }));
    open(url);
    await screen.findByText("Con trỏ lưu địa chỉ của một ô nhớ.");
    vi.stubGlobal("fetch", fetchAudio);
    fireEvent.click(screen.getByRole("button", { name: /Nghe ghi âm/ }));
    expect(await screen.findByLabelText("Ghi âm lượt này")).toBeTruthy();
    const [path, init] = fetchAudio.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/v1/turns/t2/audio");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer acc-1");
  });

  it("ghi âm đã quá hạn thì báo rõ", async () => {
    mockApi(base);
    open(url);
    await screen.findByText("Con trỏ lưu địa chỉ của một ô nhớ.");
    vi.stubGlobal("fetch", vi.fn(async () => err(404, "AUDIO_NOT_AVAILABLE")));
    fireEvent.click(screen.getByRole("button", { name: /Nghe ghi âm/ }));
    await waitFor(() => expect(screen.getByText(/Ghi âm không còn/)).toBeTruthy());
  });

  it("mở không kèm lớp / SV thì hướng dẫn quay lại hồ sơ", async () => {
    mockApi(base);
    open("/gv/sessions/s1");
    expect(await screen.findByText(/Hãy mở từ hồ sơ sinh viên/)).toBeTruthy();
  });
});
