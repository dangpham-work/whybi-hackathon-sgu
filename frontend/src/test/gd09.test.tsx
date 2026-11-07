import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { setToken } from "../lib/api";
import { auth } from "../lib/auth";
import { routes } from "../router";
import { err, mockApi, ok } from "./mock-api";

// Thay khung vẽ bằng bản giả để test bấm chọn nút / nối cạnh (React Flow không chạy trong jsdom)
vi.mock("../components/SkillTree", async (orig) => ({
  ...(await orig<typeof import("../components/SkillTree")>()),
  SkillTree: (p: {
    nodes: { key: string; title: string }[];
    onNodeClick?: (n: { key: string }) => void;
    onConnect?: (a: string, b: string) => void;
  }) => (
    <div>
      {p.nodes.map((n) => (
        <button key={n.key} onClick={() => p.onNodeClick?.(n)}>{`nút ${n.title}`}</button>
      ))}
      <button onClick={() => p.onConnect?.("n2", "n1")}>nối n2→n1</button>
    </div>
  ),
}));

const rubric = (approved: boolean) => ({
  keyPoints: [{ id: "KP1", content: "Con trỏ lưu địa chỉ", isRequired: true }],
  optionalPoints: [],
  misconceptions: [],
  scenarios: [],
  targetBloom: "UNDERSTAND",
  passThreshold: 70,
  minChallenges: 3,
  minPassedChallenges: 2,
  sourcePages: [],
  approved,
});
const TREE = (status = "DRAFT") => ({
  id: "v1",
  classId: "c1",
  versionNo: 2,
  status,
  nodes: [
    { id: "id1", key: "n1", code: "N1", title: "Biến", bloomLevel: "REMEMBER", rubric: rubric(true) },
    { id: "id2", key: "n2", code: "N2", title: "Con trỏ", bloomLevel: "UNDERSTAND", rubric: rubric(false) },
  ],
  edges: [{ id: "e1", fromKey: "n1", toKey: "n2", source: "AI" }],
});
const me = { "GET /me": ok({ id: "u", fullName: "GV", email: "g@x.vn", role: "LECTURER" }) };

function open() {
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/gv/classes/c1/tree"] })} />);
}
beforeEach(() => {
  auth.reset();
  setToken("acc-1");
});
afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

describe("GV-04 Trình sửa cây và rubric (GD-09)", () => {
  it("báo nút chưa duyệt rubric và chặn nói rõ lý do (BR-05)", async () => {
    mockApi({ ...me, "GET /classes/c1/tree": ok(TREE()) });
    open();
    expect(await screen.findByText(/1 nút chưa duyệt rubric: N2/)).toBeTruthy();
  });

  it("tạo chu trình thì thông báo chỉ rõ đường đi", async () => {
    mockApi({
      ...me,
      "GET /classes/c1/tree": ok(TREE()),
      "POST /tree-versions/v1/edges": err(409, "CYCLE_DETECTED", "cycle", { path: ["n2", "n1", "n2"] }),
    });
    open();
    fireEvent.click(await screen.findByText("nối n2→n1"));
    expect(await screen.findByText(/Cạnh này tạo chu trình: Con trỏ → Biến → Con trỏ/)).toBeTruthy();
  });

  it("nối cạnh hợp lệ thì thêm vào cây", async () => {
    const m = mockApi({
      ...me,
      "GET /classes/c1/tree": ok({ ...TREE(), edges: [] }),
      "POST /tree-versions/v1/edges": ok({ id: "e9", fromKey: "n2", toKey: "n1", source: "LECTURER" }, 201),
    });
    open();
    fireEvent.click(await screen.findByText("nối n2→n1"));
    await waitFor(() => expect(m.called("POST /tree-versions/v1/edges")).toHaveLength(1));
    expect(m.called("POST /tree-versions/v1/edges")[0].body).toEqual({ fromKey: "n2", toKey: "n1", source: "LECTURER" });
  });

  it("duyệt rubric gửi approved=true và hết cảnh báo", async () => {
    const m = mockApi({
      ...me,
      "GET /classes/c1/tree": ok(TREE()),
      "PUT /nodes/id2/rubric": ({ body }) => ok(body),
    });
    open();
    fireEvent.click(await screen.findByText("nút Con trỏ"));
    fireEvent.click(await screen.findByRole("button", { name: /Duyệt rubric/ }));
    await waitFor(() => expect(m.called("PUT /nodes/id2/rubric")).toHaveLength(1));
    expect((m.called("PUT /nodes/id2/rubric")[0].body as { approved: boolean }).approved).toBe(true);
    expect(await screen.findByText("Mọi rubric đã duyệt")).toBeTruthy();
  });

  it("sửa ý chính rồi lưu nháp thì rubric vẫn chưa duyệt", async () => {
    const m = mockApi({ ...me, "GET /classes/c1/tree": ok(TREE()), "PUT /nodes/id1/rubric": ({ body }) => ok(body) });
    open();
    fireEvent.click(await screen.findByText("nút Biến"));
    fireEvent.change(await screen.findByLabelText("Nội dung ý KP1"), { target: { value: "Biến là ô nhớ có tên" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu nháp" }));
    await waitFor(() => expect(m.called("PUT /nodes/id1/rubric")).toHaveLength(1));
    const sent = m.called("PUT /nodes/id1/rubric")[0].body as { approved: boolean; keyPoints: { content: string }[] };
    expect(sent.approved).toBe(false);
    expect(sent.keyPoints[0].content).toBe("Biến là ô nhớ có tên");
  });

  it("phát hành thất bại thì liệt kê lỗi kiểm tra", async () => {
    mockApi({
      ...me,
      "GET /classes/c1/tree": ok(TREE()),
      "POST /tree-versions/v1/publish": err(422, "PUBLISH_CHECK_FAILED", "x", { errors: ["Rubric N2 chưa duyệt"] }),
    });
    open();
    fireEvent.click(await screen.findByRole("button", { name: /Phát hành/ }));
    expect(await screen.findAllByText(/Rubric N2 chưa duyệt/)).toBeTruthy();
  });

  it("bản đã phát hành khóa sửa và cho tạo bản nháp", async () => {
    const m = mockApi({
      ...me,
      "GET /classes/c1/tree": ok(TREE("PUBLISHED")),
      "POST /classes/c1/tree-versions": ok({ ...TREE("DRAFT"), id: "v2", versionNo: 3 }, 201),
    });
    open();
    expect((await screen.findByRole("button", { name: /Thêm nút/ }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Tạo bản nháp để sửa" }));
    await waitFor(() => expect(m.called("POST /classes/c1/tree-versions")).toHaveLength(1));
    await waitFor(() => expect((screen.getByRole("button", { name: /Thêm nút/ }) as HTMLButtonElement).disabled).toBe(false));
  });
});

describe("GV-04 lịch sử, so sánh, khôi phục (GD-14)", () => {
  const V = (id: string, no: number, status: string) => ({ ...TREE(status), id, versionNo: no });
  const hist = { ...me, "GET /classes/c1/tree": ok(TREE()), "GET /classes/c1/tree-versions": ok([V("v2", 2, "DRAFT"), V("v1", 1, "PUBLISHED")]) };

  it("so sánh hai phiên bản theo tên nút", async () => {
    const m = mockApi({
      ...hist,
      "GET /tree-versions/v1/compare/v2": ok({ fromVersionNo: 1, toVersionNo: 2, nodesAdded: ["n2"], nodesRemoved: [], nodesChanged: ["n1"], edgesAdded: [{ fromKey: "n1", toKey: "n2" }], edgesRemoved: [] }),
    });
    open();
    fireEvent.click(await screen.findByRole("button", { name: /Lịch sử/ }));
    fireEvent.click(await screen.findByLabelText("Chọn v2 để so sánh"));
    fireEvent.click(screen.getByLabelText("Chọn v1 để so sánh"));
    fireEvent.click(screen.getByRole("button", { name: /So sánh 2 phiên bản/ }));
    const res = await screen.findByRole("region", { name: "Kết quả so sánh" });
    expect(res.textContent).toMatch(/v1 → v2/);
    expect(res.textContent).toMatch(/Nút thêm \(1\): Con trỏ/);
    expect(res.textContent).toMatch(/Nút đổi \(1\): Biến/);
    expect(res.textContent).toMatch(/Cạnh thêm \(1\): Biến → Con trỏ/);
    expect(m.called("GET /tree-versions/v1/compare/v2")).toHaveLength(1);
  });

  it("khôi phục bản cũ thành bản nháp mới và chuyển sang sửa", async () => {
    const m = mockApi({ ...hist, "POST /tree-versions/v1/restore": ok({ ...V("v3", 3, "DRAFT") }, 201) });
    open();
    fireEvent.click(await screen.findByRole("button", { name: /Lịch sử/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Khôi phục v1" }));
    await waitFor(() => expect(m.called("POST /tree-versions/v1/restore")).toHaveLength(1));
    expect(await screen.findByText(/Đã khôi phục thành bản nháp v3/)).toBeTruthy();
    expect(screen.getByText(/v3 · Bản nháp/)).toBeTruthy();
  });

  it("chỉ so sánh được khi chọn đúng 2 bản", async () => {
    mockApi(hist);
    open();
    fireEvent.click(await screen.findByRole("button", { name: /Lịch sử/ }));
    fireEvent.click(await screen.findByLabelText("Chọn v1 để so sánh"));
    expect((screen.getByRole("button", { name: /So sánh 2 phiên bản/ }) as HTMLButtonElement).disabled).toBe(true);
  });
});
