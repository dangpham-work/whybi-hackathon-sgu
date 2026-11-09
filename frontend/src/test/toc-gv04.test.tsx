import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { setToken } from "../lib/api";
import { auth } from "../lib/auth";
import { routes } from "../router";
import { mockApi, ok } from "./mock-api";

vi.mock("../components/SkillTree", () => ({ SkillTree: () => <div>khung cây</div>, BLOOM_LABEL: {} }));

const RUBRIC = { keyPoints: [], optionalPoints: [], misconceptions: [], scenarios: [], targetBloom: "UNDERSTAND", passThreshold: 70, minChallenges: 3, minPassedChallenges: 2, sourcePages: [], approved: false };
const node = (key: string, rubric?: unknown) => ({ id: `id-${key}`, key, code: key.toUpperCase(), title: `Nút ${key}`, bloomLevel: "UNDERSTAND", ...(rubric ? { rubric } : {}) });
const TREE = (nodes: unknown[], status = "DRAFT") => ({ id: "v1", classId: "c1", versionNo: 1, status, nodes, edges: [] });
const me = { "GET /me": ok({ id: "u", fullName: "Bình", email: "b@x.vn", role: "LECTURER" }) };

beforeEach(() => {
  auth.reset();
  setToken("acc-1");
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  setToken(null);
});

describe("GV-04 sinh rubric cho nút còn thiếu (sau khi dựng với 'chưa sinh rubric')", () => {
  it("hiện số nút thiếu rubric, bấm thì xếp hàng rồi rubric hiện dần khi hỏi lại cây", async () => {
    let gets = 0;
    const m = mockApi({
      ...me,
      "GET /classes/c1/tree": () => ok(++gets === 1 ? TREE([node("a"), node("b")]) : TREE([node("a", RUBRIC), node("b", RUBRIC)])),
      "POST /classes/c1/tree/rubrics/generate-missing": ok({ missing: 2 }, 202),
    });
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/gv/classes/c1/tree"] })} />);
    expect(await screen.findByText("2 nút chưa có rubric")).toBeTruthy();

    vi.useFakeTimers({ shouldAdvanceTime: true });
    fireEvent.click(screen.getByRole("button", { name: "Sinh rubric cho nút còn thiếu" }));
    await waitFor(() => expect(m.called("POST /classes/c1/tree/rubrics/generate-missing")).toHaveLength(1));
    expect(await screen.findByText(/Đã xếp hàng sinh rubric cho 2 nút/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Đang sinh rubric…" }) as HTMLButtonElement).disabled).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(await screen.findByText(/AI đã sinh rubric cho mọi nút/)).toBeTruthy();
    expect(screen.queryByText(/nút chưa có rubric/)).toBeNull();
  });

  it("mọi nút đã có rubric hoặc cây đã phát hành thì không có nút", async () => {
    mockApi({ ...me, "GET /classes/c1/tree": ok(TREE([node("a", RUBRIC)])) });
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/gv/classes/c1/tree"] })} />);
    await screen.findByText("khung cây");
    expect(screen.queryByRole("button", { name: "Sinh rubric cho nút còn thiếu" })).toBeNull();
  });
});
