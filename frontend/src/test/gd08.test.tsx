import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { TranscriptConfirm } from "../components/TranscriptConfirm";
import { setToken } from "../lib/api";
import { auth } from "../lib/auth";
import { editRatio, markUncertain } from "../lib/transcript";
import { routes } from "../router";
import { err, mockApi, ok } from "./mock-api";

const transcript = {
  text: "Con trỏ giữ địa chỉ, khi gọi phờ ri thì vùng nhớ được trả lại",
  confidence: 0.71,
  words: [],
  lowConfidenceWords: ["phờ", "ri"],
  audioRef: "unsaved:1",
  needsConfirmation: true,
};

describe("lib/transcript", () => {
  it("đo mức sửa theo từ", () => {
    expect(editRatio("a b c d", "a b c d")).toBe(0);
    expect(editRatio("a b c d", "a b x d")).toBe(0.25);
    expect(editRatio("a b", "")).toBe(1);
  });
  it("đánh dấu từ không chắc, bỏ qua dấu câu và hoa thường", () => {
    const m = markUncertain("Khi gọi Phờ, ri", ["phờ", "ri"]).filter((p) => p.uncertain);
    expect(m.map((p) => p.text)).toEqual(["Phờ,", "ri"]);
  });
});

describe("SV-05 Xác nhận bản chép lời (GD-08)", () => {
  const setup = () => {
    const onConfirm = vi.fn();
    render(<TranscriptConfirm transcript={transcript} onConfirm={onConfirm} onRetry={vi.fn()} onCancel={vi.fn()} />);
    return onConfirm;
  };

  it("gạch chân từ không chắc và hiện độ tin cậy", () => {
    setup();
    expect(screen.getByText("0,71")).toBeTruthy();
    expect(document.querySelectorAll("u")).toHaveLength(2);
  });

  it("sửa nhỏ được ghi nhận là đã sửa", () => {
    const onConfirm = setup();
    fireEvent.change(screen.getByLabelText(/Bản chép lời/), { target: { value: transcript.text.replace("phờ ri", "free()") } });
    fireEvent.click(screen.getByRole("button", { name: /Xác nhận và gửi/ }));
    expect(onConfirm).toHaveBeenCalledWith(transcript.text.replace("phờ ri", "free()"), true);
  });

  it("không sửa thì gửi nguyên văn, edited=false", () => {
    const onConfirm = setup();
    fireEvent.click(screen.getByRole("button", { name: /Xác nhận và gửi/ }));
    expect(onConfirm).toHaveBeenCalledWith(transcript.text, false);
  });

  it("viết lại gần hết thì chặn gửi và bảo ghi âm lại", () => {
    setup();
    fireEvent.change(screen.getByLabelText(/Bản chép lời/), { target: { value: "một đoạn hoàn toàn khác do tôi tự viết lại" } });
    expect(screen.getByRole("alert").textContent).toMatch(/ghi âm lại/);
    expect((screen.getByRole("button", { name: /Xác nhận và gửi/ }) as HTMLButtonElement).disabled).toBe(true);
  });
});

const RESULT = {
  sessionId: "s1",
  studentId: "u",
  nodeId: "n5",
  classId: "c1",
  state: "MASTERED",
  verdict: "PASSED",
  totalScore: 78,
  passThreshold: 70,
  criteria: [
    { code: "CORRECTNESS", weight: 0.25, score: 22, max: 25 },
    { code: "COVERAGE", weight: 0.25, score: 20, max: 25, rationale: "Thiếu: con trỏ có kiểu dữ liệu" },
    { code: "ESSENCE", weight: 0.2, score: 15, max: 20 },
    { code: "ROBUSTNESS", weight: 0.2, score: 14, max: 20 },
    { code: "CLARITY", weight: 0.1, score: 7, max: 10 },
  ],
  strengths: ["Giải thích đúng con trỏ treo."],
  reviewHints: ["Vì sao con trỏ cần có kiểu?"],
  sourcePages: [12, 13],
  unlockedNodes: ["n6"],
  flags: ["PASTE_SUSPECTED"],
  isPeerFollowup: false,
  detectedMisconceptions: [],
};

function open(url: string) {
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [url] })} />);
}
beforeEach(() => {
  auth.reset();
  setToken("acc-1");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  setToken(null);
});

describe("SV-06 Kết quả và phản hồi (GD-08)", () => {
  it("hiện đủ 5 tiêu chí, điểm, điều làm tốt và gợi ý ôn", async () => {
    mockApi({ "GET /sessions/s1/result": ok(RESULT) });
    open("/sv/sessions/s1/result");
    expect(await screen.findByText("78/100")).toBeTruthy();
    expect(screen.getAllByRole("progressbar")).toHaveLength(5);
    expect(screen.getByText("22/25")).toBeTruthy();
    expect(screen.getByText("Thiếu: con trỏ có kiểu dữ liệu")).toBeTruthy();
    expect(screen.getByText("Giải thích đúng con trỏ treo.")).toBeTruthy();
    expect(screen.getByText(/Vì sao con trỏ cần có kiểu/)).toBeTruthy();
    expect(screen.getByText(/trang 12, 13/)).toBeTruthy();
    expect(screen.getByText(/dán văn bản dài/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Giảng nút tiếp theo/ }).getAttribute("href")).toBe("/sv/classes/c1/nodes/n6");
  });

  it("chưa Đạt thì ghi rõ và gợi ý giảng lại", async () => {
    mockApi({ "GET /sessions/s1/result": ok({ ...RESULT, verdict: "FAILED", totalScore: 41, unlockedNodes: [], flags: [] }) });
    open("/sv/sessions/s1/result");
    expect(await screen.findByText("CHƯA ĐẠT")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Giảng lại/ })).toBeTruthy();
  });

  it("chưa chấm xong (409) thì chờ rồi tự tải lại", async () => {
    let n = 0;
    mockApi({ "GET /sessions/s1/result": () => (n++ === 0 ? err(409, "RESULT_NOT_READY") : ok(RESULT)) });
    open("/sv/sessions/s1/result");
    expect(await screen.findByText(/đang chấm lời giảng/)).toBeTruthy();
    expect(await screen.findByText("78/100", {}, { timeout: 5000 })).toBeTruthy();
  }, 10000);
});

describe("SV-05 mở thẳng đường dẫn", () => {
  it("quay về phiên giảng", async () => {
    mockApi({});
    const router = createMemoryRouter(routes, { initialEntries: ["/sv/sessions/s1/transcript"] });
    render(<RouterProvider router={router} />);
    await waitFor(() => expect(router.state.location.pathname).toBe("/sv/sessions/s1"));
  });
});
