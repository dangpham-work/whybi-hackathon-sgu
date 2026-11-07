import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { setToken } from "../lib/api";
import { auth } from "../lib/auth";
import { mmss } from "../lib/countdown";
import { routes } from "../router";
import { err, mockApi, ok } from "./mock-api";

type Handler = (e: { channel: string; event: string; payload: unknown }) => void;
const handlers: Record<string, Handler> = {};
// chuông thông báo cũng gọi useChannel nên giữ handler theo kênh, đẩy tin vào đúng kênh phiên
const push: Handler = (e) => handlers["session:s1"]?.(e);
vi.mock("../lib/ws", async (orig) => ({
  ...(await orig<typeof import("../lib/ws")>()),
  useChannel: (c: string | null, h: Handler) => {
    if (c) handlers[c] = h;
    return "open";
  },
}));

const student = { "GET /me": ok({ id: "u", fullName: "SV", email: "s@x.vn", role: "STUDENT" }) };
const soon = (ms: number) => new Date(Date.now() + ms).toISOString();
function open(state: object) {
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [{ pathname: "/sv/sessions/s1", state }] })} />);
}
beforeEach(() => {
  auth.reset();
  setToken("acc-1");
});
afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

it("mmss định dạng phút:giây", () => {
  expect(mmss(95)).toBe("01:35");
  expect(mmss(0)).toBe("00:00");
});

describe("SV-04 đồng hồ đếm giờ (GD-12)", () => {
  it("hiện đồng hồ cho câu có hạn; câu mở đầu không hạn thì không hiện", async () => {
    mockApi(student);
    open({ opening: { text: "Bạn giảng giúp mình nhé?" } });
    await screen.findByText("Bạn giảng giúp mình nhé?");
    expect(screen.queryByRole("timer")).toBeNull();
    act(() => push({ channel: "session:s1", event: "session.question", payload: { text: "Nếu hai con trỏ cùng trỏ một ô nhớ?", deadline: soon(90_000) } }));
    expect((await screen.findByRole("timer")).textContent).toMatch(/01:(29|30)/);
  });

  it("đồng hồ về 0 thì gọi /timeout đúng một lần, ghi nhận hết giờ và sang câu kế", async () => {
    const m = mockApi({
      ...student,
      "POST /sessions/s1/timeout": ok({ status: "CHALLENGING", question: { text: "Câu kế tiếp?", deadline: soon(60_000) }, notice: "Câu này hết giờ nên được tính là chưa trả lời.", questionsAsked: 2, questionsTotal: 3 }),
    });
    open({ opening: { text: "Mở đầu", deadline: soon(600) } });
    await waitFor(() => expect(m.called("POST /sessions/s1/timeout")).toHaveLength(1), { timeout: 3000 });
    expect(await screen.findByText(/hết giờ nên được tính là chưa trả lời/)).toBeTruthy();
    expect(await screen.findByText("Câu kế tiếp?")).toBeTruthy();
    await new Promise((r) => setTimeout(r, 600));
    expect(m.called("POST /sessions/s1/timeout")).toHaveLength(1);
  });

  it("máy chủ từ chối timeout thì báo lỗi, không gọi lặp", async () => {
    const m = mockApi({ ...student, "POST /sessions/s1/timeout": err(409, "SESSION_NOT_ACTIVE") });
    open({ opening: { text: "Mở đầu", deadline: soon(400) } });
    expect(await screen.findByText(/đã kết thúc/, {}, { timeout: 3000 })).toBeTruthy();
    expect(m.called("POST /sessions/s1/timeout")).toHaveLength(1);
  });
});

describe("SV-04 bật / tắt đọc câu hỏi (GD-12)", () => {
  const stubAudio = () => {
    const played = vi.fn(async () => {});
    class FakeAudio {
      play = played;
      pause = vi.fn();
      constructor(public src: string) {}
    }
    vi.stubGlobal("Audio", FakeAudio);
    URL.createObjectURL = vi.fn(() => "blob:tts");
    return played;
  };

  it("bật thì câu hỏi tới sau được đọc (tải bằng token); tắt thì không", async () => {
    mockApi(student);
    const played = stubAudio();
    const fetchAudio = vi.fn(async () => new Response(new Blob(["x"]), { status: 200 }));
    open({ opening: { text: "Mở đầu" } });
    await screen.findByText("Mở đầu");
    vi.stubGlobal("fetch", fetchAudio);

    const toggle = screen.getByRole("button", { name: /Đọc câu hỏi/ });
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    act(() => push({ channel: "x", event: "session.question", payload: { text: "Câu 1 chưa bật", audioUrl: "/api/v1/sessions/s1/turns/1/tts" } }));
    await screen.findByText("Câu 1 chưa bật");
    expect(fetchAudio).not.toHaveBeenCalled();

    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-pressed")).toBe("true");
    act(() => push({ channel: "x", event: "session.question", payload: { text: "Câu 2 đã bật", audioUrl: "/api/v1/sessions/s1/turns/2/tts" } }));
    await waitFor(() => expect(played).toHaveBeenCalledTimes(1));
    expect((fetchAudio.mock.calls[0] as unknown as [string, RequestInit])[0]).toBe("/api/v1/sessions/s1/turns/2/tts");
  });

  it("TTS lỗi thì phiên vẫn chạy bình thường", async () => {
    mockApi(student);
    stubAudio();
    open({ opening: { text: "Mở đầu" }, ttsEnabled: true });
    await screen.findByText("Mở đầu");
    vi.stubGlobal("fetch", vi.fn(async () => err(503, "TTS_UNAVAILABLE")));
    act(() => push({ channel: "x", event: "session.question", payload: { text: "Câu lỗi tiếng", audioUrl: "/api/v1/sessions/s1/turns/3/tts" } }));
    expect(await screen.findByText("Câu lỗi tiếng")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("GV-09 điều chỉnh cặp thủ công (GD-12)", () => {
  const lecturer = { "GET /me": ok({ id: "u", fullName: "GV", email: "g@x.vn", role: "LECTURER" }), "GET /notifications": ok([]) };
  const M = { id: "m1", partnerId: "b", partnerName: "B", iTeach: [], iLearn: [], status: "PROPOSED", weight: 3, expiresAt: "", oneWay: false, acceptedByMe: false, studiedByMe: false, studentAId: "a", studentAName: "Trần Bảo Châu", studentBId: "b", studentBName: "Nguyễn Minh An", items: [], createdAt: "" };
  const GRID = { grid: [{ studentId: "a", studentName: "Trần Bảo Châu" }, { studentId: "b", studentName: "Nguyễn Minh An" }, { studentId: "c", studentName: "Lê Hoàng Dũng" }] };
  const base = {
    ...lecturer,
    "GET /classes/c1/matches": ok([M]),
    "GET /classes/c1/tree": ok({ id: "v", versionNo: 1, status: "PUBLISHED", nodes: [], edges: [] }),
    "GET /classes/c1/matching-stats": ok({ totalMatches: 1, accepted: 0, declined: 0, expired: 0, studied: 0, itemsTotal: 0, itemsVerified: 0, acceptRate: 0, studiedRate: 0, verifiedRate: 0 }),
    "GET /classes/c1/heatmap": ok(GRID),
  };
  const openPanel = async () => {
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/gv/classes/c1/matching"] })} />);
    fireEvent.click(await screen.findByRole("button", { name: /Điều chỉnh cặp Trần Bảo Châu/ }));
  };

  it("thay một SV: gửi replaceStudentId + withStudentId, chỉ cho chọn SV ngoài cặp", async () => {
    const m = mockApi({ ...base, "PATCH /matches/m1": ok({ ...M, studentBId: "c" }) });
    await openPanel();
    const sel = await screen.findByLabelText("Sinh viên thay thế");
    expect(Array.from((sel as HTMLSelectElement).options).map((o) => o.text)).toEqual(["Chọn sinh viên…", "Lê Hoàng Dũng"]);
    fireEvent.change(sel, { target: { value: "c" } });
    fireEvent.change(screen.getByLabelText("Sinh viên được thay"), { target: { value: "b" } });
    fireEvent.click(screen.getByRole("button", { name: "Thay sinh viên" }));
    await waitFor(() => expect(m.called("PATCH /matches/m1")).toHaveLength(1));
    expect(m.called("PATCH /matches/m1")[0].body).toEqual({ cancel: false, replaceStudentId: "b", withStudentId: "c" });
  });

  it("hủy cặp gửi cancel=true", async () => {
    const m = mockApi({ ...base, "PATCH /matches/m1": ok({ ...M, status: "DECLINED" }) });
    await openPanel();
    fireEvent.click(await screen.findByRole("button", { name: "Hủy cặp" }));
    await waitFor(() => expect(m.called("PATCH /matches/m1")).toHaveLength(1));
    expect(m.called("PATCH /matches/m1")[0].body).toEqual({ cancel: true });
  });

  it("SV được chọn đang bận thì báo bằng câu dễ hiểu", async () => {
    mockApi({ ...base, "PATCH /matches/m1": err(409, "STUDENT_BUSY") });
    await openPanel();
    fireEvent.change(await screen.findByLabelText("Sinh viên thay thế"), { target: { value: "c" } });
    fireEvent.click(screen.getByRole("button", { name: "Thay sinh viên" }));
    expect(await screen.findByText(/đang trong một cặp hoạt động khác/)).toBeTruthy();
  });
});
