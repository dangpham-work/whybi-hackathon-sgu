import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { setToken } from "../lib/api";
import { auth } from "../lib/auth";
import { routes } from "../router";
import { checkSettings } from "../pages/lecturer/GV10";
import { err, mockApi, ok } from "./mock-api";

const SETTINGS = { passThreshold: 70, greenThreshold: 0.7, yellowThreshold: 0.4, minSample: 5, challengeCount: 3 };
const open = (url: string) => render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [url] })} />);
beforeEach(() => {
  auth.reset();
  setToken("acc-1");
});
afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

describe("checkSettings", () => {
  it("bắt các giá trị backend sẽ từ chối", () => {
    expect(checkSettings(SETTINGS)).toBeNull();
    expect(checkSettings({ ...SETTINGS, yellowThreshold: 0.8 })).toMatch(/Ngưỡng vàng/);
    expect(checkSettings({ ...SETTINGS, challengeCount: 6 })).toMatch(/3 đến 5/);
    expect(checkSettings({ ...SETTINGS, minSample: 0 })).toMatch(/Cỡ mẫu/);
  });
});

describe("GV-10 Cấu hình ngưỡng (GD-14)", () => {
  const lecturer = { "GET /me": ok({ id: "u", fullName: "GV", email: "g@x.vn", role: "LECTURER" }) };

  it("nạp cấu hình hiện tại (ngưỡng hiển thị theo %) và lưu thay đổi", async () => {
    const m = mockApi({ ...lecturer, "GET /classes/c1/settings": ok(SETTINGS), "PUT /classes/c1/settings": ({ body }) => ok(body) });
    open("/gv/classes/c1/settings");
    const green = (await screen.findByLabelText(/Ngưỡng xanh/)) as HTMLInputElement;
    expect(green.value).toBe("70");
    fireEvent.change(green, { target: { value: "80" } });
    fireEvent.change(screen.getByLabelText(/Số câu phản biện/), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: /Lưu cấu hình/ }));
    expect(await screen.findByText(/Đã lưu cấu hình/)).toBeTruthy();
    expect(m.called("PUT /classes/c1/settings")[0].body).toEqual({ ...SETTINGS, greenThreshold: 0.8, challengeCount: 4 });
  });

  it("ngưỡng vàng cao hơn ngưỡng xanh thì chặn và không gọi API", async () => {
    const m = mockApi({ ...lecturer, "GET /classes/c1/settings": ok(SETTINGS) });
    open("/gv/classes/c1/settings");
    fireEvent.change(await screen.findByLabelText(/Ngưỡng vàng/), { target: { value: "90" } });
    fireEvent.click(screen.getByRole("button", { name: /Lưu cấu hình/ }));
    expect(await screen.findByText(/Ngưỡng vàng không được cao hơn/)).toBeTruthy();
    expect(m.called("PUT /classes/c1/settings")).toHaveLength(0);
  });

  it("máy chủ từ chối (422) thì báo lỗi", async () => {
    mockApi({ ...lecturer, "GET /classes/c1/settings": ok(SETTINGS), "PUT /classes/c1/settings": err(422, "VALIDATION_ERROR") });
    open("/gv/classes/c1/settings");
    fireEvent.click(await screen.findByRole("button", { name: /Lưu cấu hình/ }));
    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});

describe("SV-08 Lịch sử phiên (GD-16)", () => {
  const student = { "GET /me": ok({ id: "u", fullName: "SV", email: "s@x.vn", role: "STUDENT" }) };
  const R = (id: string, verdict: string, score: number) => ({ sessionId: id, studentId: "u", nodeId: "n", classId: "c1", state: "X", verdict, totalScore: score, passThreshold: 70, criteria: [], strengths: [], reviewHints: [], sourcePages: [], unlockedNodes: [], flags: [], isPeerFollowup: false, detectedMisconceptions: [], completedAt: "2026-10-13T07:20:00Z" });

  it("tổng hợp số phiên, Đạt, điểm TB và lọc theo kết quả", async () => {
    mockApi({ ...student, "GET /me/sessions": ok([R("a", "PASSED", 80), R("b", "FAILED", 60), R("c", "PASSED", 70)]) });
    open("/sv/history");
    const list = await screen.findByRole("list", { name: "Các phiên" });
    expect(list.querySelectorAll(":scope > li")).toHaveLength(3);
    expect(screen.getByText("70", { selector: "dd" })).toBeTruthy(); // điểm TB (80+60+70)/3
    fireEvent.click(screen.getByRole("button", { name: "Chưa đạt" }));
    expect(list.querySelectorAll(":scope > li")).toHaveLength(1);
  });

  it("mở một phiên thì tải hội thoại và có nút nghe ghi âm", async () => {
    mockApi({
      ...student,
      "GET /me/sessions": ok([R("a", "PASSED", 80)]),
      "GET /me/sessions/a": ok({ sessionId: "a", nodeId: "n", nodeTitle: "Con trỏ", attemptNo: 1, status: "COMPLETED", startedAt: "", turns: [{ turnNo: 1, speaker: "STUDENT", turnType: "EXPLANATION", content: "Con trỏ lưu địa chỉ", inputMode: "VOICE", audioUrl: "/api/v1/turns/t1/audio", createdAt: "" }] }),
    });
    open("/sv/history");
    fireEvent.click(await screen.findByRole("button", { name: /Đạt · 80\/100/ }));
    expect(await screen.findByText("Con trỏ lưu địa chỉ")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Nghe ghi âm/ })).toBeTruthy();
    expect(screen.getByText("Con trỏ")).toBeTruthy();
  });

  it("chưa có phiên nào thì nhắc giảng một nút", async () => {
    mockApi({ ...student, "GET /me/sessions": ok([]) });
    open("/sv/history");
    await waitFor(() => expect(screen.getByText(/chưa có phiên nào được chấm/)).toBeTruthy());
  });
});
