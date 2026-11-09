import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { setToken } from "../lib/api";
import { auth } from "../lib/auth";
import { remaining } from "../lib/matching";
import { routes } from "../router";
import { err, mockApi, ok } from "./mock-api";

const TREE = {
  id: "v1",
  versionNo: 1,
  status: "PUBLISHED",
  nodes: [
    { id: "i4", key: "n4", code: "N4", title: "Đệ quy", bloomLevel: "ANALYZE" },
    { id: "i5", key: "n5", code: "N5", title: "Con trỏ", bloomLevel: "UNDERSTAND" },
  ],
  edges: [],
};
const MATCH = {
  id: "m1",
  partnerId: "an",
  partnerName: "Nguyễn Minh An",
  iTeach: ["n4"],
  iLearn: ["n5"],
  status: "PROPOSED",
  weight: 3.8,
  expiresAt: new Date(Date.now() + 41.5 * 3_600_000).toISOString(),
  oneWay: false,
  acceptedByMe: false,
  studiedByMe: false,
  studentAId: "chau",
  studentAName: "Trần Bảo Châu",
  studentBId: "an",
  studentBName: "Nguyễn Minh An",
  items: [],
  createdAt: new Date().toISOString(),
};
const me = (role: string) => ({ "GET /me": ok({ id: "u", fullName: "X", email: "x@x.vn", role }) });
const open = (url: string) => render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [url] })} />);
beforeEach(() => {
  auth.reset();
  setToken("acc-1");
});
afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

describe("lib/matching", () => {
  it("remaining: giờ, ngày, hết hạn", () => {
    const now = Date.parse("2026-10-24T00:00:00Z");
    expect(remaining("2026-10-25T17:00:00Z", now)).toBe("còn 41 giờ");
    expect(remaining("2026-10-31T00:00:00Z", now)).toBe("còn 7 ngày");
    expect(remaining("2026-10-23T00:00:00Z", now)).toBe("đã hết hạn");
  });
});

describe("GV-09 Quản lý ghép cặp (GD-11)", () => {
  const routes_ = {
    ...me("LECTURER"),
    "GET /classes/c1/matches": ok([MATCH]),
    "GET /classes/c1/tree": ok(TREE),
    "GET /classes/c1/matching-stats": ok({ totalMatches: 21, accepted: 16, declined: 3, expired: 2, studied: 12, itemsTotal: 12, itemsVerified: 7, acceptRate: 0.76, studiedRate: 0.75, verifiedRate: 0.58 }),
  };

  it("hiện đúng cặp An ↔ Châu với nút dạy–học và thống kê", async () => {
    mockApi(routes_);
    open("/gv/classes/c1/matching");
    const table = await screen.findByRole("table");
    const row = within(table).getByText("Trần Bảo Châu").closest("tr")!;
    expect(within(row).getByText("Nguyễn Minh An")).toBeTruthy();
    expect(within(row).getByText(/→ N4 Đệ quy/)).toBeTruthy();
    expect(within(row).getByText(/→ N5 Con trỏ/)).toBeTruthy();
    expect(within(row).getByText("Chờ phản hồi")).toBeTruthy();
    expect(within(row).getByText("3,8")).toBeTruthy();
    expect(await screen.findByText("76%")).toBeTruthy();
  });

  it("chạy vòng ghép cặp có nút ưu tiên, báo kết quả và tải lại danh sách", async () => {
    const m = mockApi({
      ...routes_,
      "POST /classes/c1/matching-rounds": ok({ id: "r1", triggerType: "MANUAL", participantCount: 38, totalWeight: 1, matches: [MATCH], waitingStudentIds: ["x", "y", "z"], createdAt: "" }, 201),
    });
    open("/gv/classes/c1/matching");
    await screen.findByRole("table");
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "i5" } });
    fireEvent.click(screen.getByRole("button", { name: /Chạy vòng ghép cặp/ }));
    expect(await screen.findByText(/Đã ghép 1 cặp từ 38 SV; 3 SV chờ vòng sau/)).toBeTruthy();
    expect(m.called("POST /classes/c1/matching-rounds")[0].body).toEqual({ priorityNodeId: "i5" });
    expect(m.called("GET /classes/c1/matches").length).toBeGreaterThan(1);
  });

  it("chưa đủ SV bật ghép cặp thì báo bằng câu dễ hiểu", async () => {
    mockApi({ ...routes_, "POST /classes/c1/matching-rounds": err(409, "NOT_ENOUGH_PARTICIPANTS", "x", { participantCount: 1 }) });
    open("/gv/classes/c1/matching");
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: /Chạy vòng ghép cặp/ }));
    expect(await screen.findByText(/Chưa đủ 2 sinh viên/)).toBeTruthy();
  });
});

describe("SV-07 Bạn cùng tiến (GD-11)", () => {
  const base = {
    ...me("STUDENT"),
    "GET /classes/c1/matches": ok([MATCH]),
    "GET /classes/c1/my-map": ok({ classId: "c1", studentId: "chau", tree: TREE, progress: [], frontier: [], masteredCount: 0, totalCount: 2 }),
  };

  it("hiện gợi ý An kèm nút dạy – học theo tên nút, thời gian ghép và hạn còn lại", async () => {
    mockApi(base);
    open("/sv/classes/c1/peers");
    expect(await screen.findByText("Nguyễn Minh An")).toBeTruthy();
    expect(await screen.findByText("Đệ quy")).toBeTruthy();
    expect(screen.getByText("Con trỏ")).toBeTruthy();
    expect(screen.getByText("Hạn: còn 41 giờ")).toBeTruthy();
    expect(screen.getByText(/Được giảng viên ghép:/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Chấp nhận/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Từ chối/ })).toBeNull();
  });

  it("lớp chưa có ghép cặp thì hiển thị 'Chưa được ghép cặp'", async () => {
    mockApi({ ...base, "GET /classes/c1/matches": ok([]) });
    open("/sv/classes/c1/peers");
    expect(await screen.findByText("Chưa được ghép cặp")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Chấp nhận/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Từ chối/ })).toBeNull();
  });

  it("hiển thị ghép cặp mới nhất ở ô chính và tab sổ xuống xem lịch sử", async () => {
    const olderMatch = { ...MATCH, id: "m2", partnerName: "Lê Văn Cũ", createdAt: "2026-11-01T10:00:00Z" };
    mockApi({ ...base, "GET /classes/c1/matches": ok([MATCH, olderMatch]) });
    open("/sv/classes/c1/peers");
    expect(await screen.findByText("Nguyễn Minh An")).toBeTruthy();
    expect(screen.getByText(/Lịch sử ghép cặp/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Lịch sử ghép cặp/ }));
    expect(await screen.findByText("Lê Văn Cũ")).toBeTruthy();
  });

  it("cặp hiển thị nút Đã học cùng và gửi action studied", async () => {
    const m = mockApi({ ...base, "POST /matches/m1/studied": ok({ ...MATCH, status: "STUDIED", studiedByMe: true }) });
    open("/sv/classes/c1/peers");
    fireEvent.click(await screen.findByRole("button", { name: /Đã học cùng/ }));
    await waitFor(() => expect(m.called("POST /matches/m1/studied")).toHaveLength(1));
  });

  it("sau khi học cùng, bấm giảng lại gắn peerMatchItemId vào phiên", async () => {
    const item = { id: "it1", teacherId: "an", learnerId: "chau", nodeId: "i5", nodeKey: "n5", verified: false };
    const m = mockApi({
      ...base,
      "GET /classes/c1/matches": ok([{ ...MATCH, status: "STUDIED", studiedByMe: true, items: [item] }]),
      "POST /sessions": ok({ sessionId: "s1", status: "EXPLAINING", opening: { text: "Chào" } }, 201),
    });
    open("/sv/classes/c1/peers");
    fireEvent.click(await screen.findByRole("button", { name: /Giảng lại Con trỏ để xác nhận/ }));
    await waitFor(() => expect(m.called("POST /sessions")).toHaveLength(1));
    expect(m.called("POST /sessions")[0].body).toMatchObject({ nodeId: "i5", peerMatchItemId: "it1" });
  });
});
