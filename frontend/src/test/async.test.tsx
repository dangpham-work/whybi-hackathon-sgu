import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AsyncView } from "../components/AsyncView";
import { ApiError, FRIENDLY } from "../lib/api";
import { useApi, useChannel } from "../lib/hooks";
import { RealtimeClient, type WsEvent } from "../lib/ws";

function Classes({ load }: { load: (signal: AbortSignal) => Promise<string[]> }) {
  const state = useApi(load, []);
  return (
    <AsyncView state={state} loadingLabel="Đang tải lớp…" empty={<p>Chưa có lớp nào.</p>}>
      {(names) => (
        <ul>
          {names.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </AsyncView>
  );
}

describe("trạng thái tải và lỗi dùng chung (GD-02)", () => {
  it("hiện đang tải rồi hiện dữ liệu", async () => {
    render(<Classes load={() => Promise.resolve(["CTDL&GT"])} />);
    expect(screen.getByRole("status").textContent).toContain("Đang tải lớp…");
    expect(await screen.findByText("CTDL&GT")).toBeTruthy();
  });

  it("dữ liệu rỗng thì hiện thông báo rỗng", async () => {
    render(<Classes load={() => Promise.resolve([])} />);
    expect(await screen.findByText("Chưa có lớp nào.")).toBeTruthy();
  });

  it("lỗi API hiện câu dễ hiểu và bấm Thử lại thì gọi lại", async () => {
    const load = vi
      .fn<(s: AbortSignal) => Promise<string[]>>()
      .mockRejectedValueOnce(new ApiError(0, "NETWORK_ERROR", FRIENDLY.NETWORK_ERROR))
      .mockResolvedValueOnce(["Lớp A"]);
    render(<Classes load={load} />);
    expect((await screen.findByRole("alert")).textContent).toContain(FRIENDLY.NETWORK_ERROR);
    fireEvent.click(screen.getByRole("button", { name: /Thử lại/ }));
    expect(await screen.findByText("Lớp A")).toBeTruthy();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("lỗi JS lạ không lộ ra người dùng", async () => {
    render(<Classes load={() => Promise.reject(new Error("x is undefined"))} />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(FRIENDLY.HTTP_ERROR);
    expect(alert.textContent).not.toContain("undefined");
  });

  it("rời trang thì hủy yêu cầu", async () => {
    let signal: AbortSignal | undefined;
    const { unmount } = render(
      <Classes
        load={(s) => {
          signal = s;
          return new Promise(() => {});
        }}
      />,
    );
    await waitFor(() => expect(signal).toBeDefined());
    unmount();
    expect(signal!.aborted).toBe(true);
  });

  it("useChannel đăng ký khi mount và hủy khi unmount", () => {
    const client = new RealtimeClient(() => null, () => null);
    const got: WsEvent[] = [];
    function Listener() {
      useChannel("job:1", (e) => got.push(e), client);
      return null;
    }
    const sub = vi.spyOn(client, "subscribe");
    const { unmount } = render(<Listener />);
    expect(sub).toHaveBeenCalledWith("job:1", expect.any(Function));
    const handler = sub.mock.calls[0][1];
    act(() => handler({ channel: "job:1", event: "job.progress", payload: 50 }));
    expect(got).toEqual([{ channel: "job:1", event: "job.progress", payload: 50 }]);
    unmount();
    // sau khi unmount, client không còn kênh nào
    expect((client as unknown as { handlers: Map<string, unknown> }).handlers.size).toBe(0);
  });
});
