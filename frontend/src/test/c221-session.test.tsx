import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import TeachingSession from "../pages/student/SV04";
import { ok } from "./mock-api";

type Event = { event: string; payload: unknown };
let push: (e: Event) => void;
vi.mock("../lib/ws", () => ({ useChannel: (_: string, handler: typeof push) => { push = handler; } }));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}
type OpenState = { opening?: { text: string; deadline?: string }; ttsEnabled?: boolean };
/** Mở SV-04; GET /sessions/s1 (khôi phục phiên, #153) trả đúng trạng thái như location state, đợi tải xong rồi mới cho test thao tác. */
async function open(extra: OpenState = {}) {
  const state = { inputMode: "TEXT", status: "CHALLENGING", opening: { text: "Câu cũ", deadline: new Date(Date.now() + 1000).toISOString() }, ...extra };
  const inner = globalThis.fetch;
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => url === "/api/v1/sessions/s1" ? Promise.resolve(ok({
    sessionId: "s1", nodeId: "n1", status: "CHALLENGING", inputMode: "TEXT", ttsEnabled: state.ttsEnabled ?? false,
    turns: [{ turnNo: 1, speaker: "TUTEE", turnType: "OPENING", text: state.opening.text, inputMode: "TEXT", createdAt: "2026-10-26T08:00:00Z" }],
    question: state.opening, questionsAsked: 1, questionsTotal: 3, startedAt: "2026-10-26T08:00:00Z",
  })) : inner(url, init));
  const view = render(<RouterProvider router={createMemoryRouter([{ path: "/sv/sessions/:sessionId", element: <TeachingSession /> }], {
    initialEntries: [{ pathname: "/sv/sessions/s1", state }],
  })} />);
  await act(async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); });
  return view;
}
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

it("C2-21 không gửi timeout trong lúc HTTP gửi lượt đang dở và không dùng hạn câu cũ sau trả lời", async () => {
  vi.useFakeTimers();
  const turn = deferred<Response>();
  const requests: string[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    requests.push(url);
    return url.endsWith("/turns") ? turn.promise : Promise.resolve(ok({ status: "CHALLENGING", questionsAsked: 2, questionsTotal: 3 }));
  }));
  await open();
  fireEvent.change(screen.getByLabelText("Câu trả lời của bạn"), { target: { value: "Câu trả lời" } });
  fireEvent.click(screen.getByRole("button", { name: "Gửi câu trả lời" }));
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(requests).toEqual(["/api/v1/sessions/s1/turns"]);
  await act(async () => { turn.resolve(ok({ status: "CHALLENGING", question: { text: "Câu mới", deadline: new Date(Date.now() + 60000).toISOString() }, questionsAsked: 2, questionsTotal: 3 })); });
  expect(screen.getByText("Câu mới")).toBeTruthy();
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(requests).toEqual(["/api/v1/sessions/s1/turns"]);
});

it("C2-21 câu mới qua WebSocket thay hạn cũ trước khi đồng hồ hết giờ", async () => {
  vi.useFakeTimers();
  const fetchMock = vi.fn(async () => ok({ status: "CHALLENGING", questionsAsked: 2, questionsTotal: 3 }));
  vi.stubGlobal("fetch", fetchMock);
  await open();
  await act(async () => { await vi.advanceTimersByTimeAsync(750); });
  act(() => push({ event: "session.question", payload: { text: "Câu mới qua WS", deadline: new Date(Date.now() + 60000).toISOString() } }));
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(screen.getByText("Câu mới qua WS")).toBeTruthy();
  expect(fetchMock).not.toHaveBeenCalled();
});

function audioMocks() {
  const played = vi.fn(async () => {});
  const paused = vi.fn();
  const audios: FakeAudio[] = [];
  class FakeAudio {
    play = played;
    pause = paused;
    onended: (() => void) | null = null;
    onerror: (() => void) | null = null;
    constructor(public src: string) { audios.push(this); }
  }
  const revoke = vi.fn();
  let id = 0;
  vi.stubGlobal("Audio", FakeAudio);
  vi.stubGlobal("URL", Object.assign(class extends URL {}, { createObjectURL: vi.fn(() => `blob:tts-${++id}`), revokeObjectURL: revoke }));
  return { played, paused, audios, revoke };
}
const audioQuestion = { text: "Câu có tiếng", audioUrl: "/api/v1/sessions/s1/turns/2/tts" };

it.each(["tắt", "unmount"])("C2-21 TTS tải chậm không phát sau %s và thu hồi blob", async (action) => {
  const { played, revoke } = audioMocks();
  const response = deferred<Response>();
  vi.stubGlobal("fetch", vi.fn(() => response.promise));
  const view = await open({ opening: { text: "Mở đầu" }, ttsEnabled: true });
  act(() => push({ event: "session.question", payload: audioQuestion }));
  if (action === "tắt") fireEvent.click(screen.getByRole("button", { name: "Đang đọc câu hỏi" }));
  else view.unmount();
  await act(async () => { response.resolve(new Response(new Blob(["audio"]))); });
  expect(played).not.toHaveBeenCalled();
  expect(revoke).toHaveBeenCalledWith("blob:tts-1");
});

it("C2-21 TTS dừng khi tắt và thu hồi blob khi phát xong", async () => {
  const { played, paused, audios, revoke } = audioMocks();
  vi.stubGlobal("fetch", vi.fn(async () => new Response(new Blob(["audio"]))));
  await open({ opening: { text: "Mở đầu" }, ttsEnabled: true });
  act(() => push({ event: "session.question", payload: audioQuestion }));
  await waitFor(() => expect(played).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "Đang đọc câu hỏi" }));
  expect(paused).toHaveBeenCalled();
  expect(revoke).toHaveBeenCalledWith("blob:tts-1");
  fireEvent.click(screen.getByRole("button", { name: "Đọc câu hỏi" }));
  act(() => push({ event: "session.question", payload: { text: "Câu kế", audioUrl: "/api/v1/sessions/s1/turns/3/tts" } }));
  await waitFor(() => expect(played).toHaveBeenCalledTimes(2));
  act(() => audios[1].onended?.());
  expect(revoke).toHaveBeenCalledWith("blob:tts-2");
});

it("C2-21 cùng câu qua WS và HTTP chỉ đọc một lần", async () => {
  const { played } = audioMocks();
  const turn = deferred<Response>();
  vi.stubGlobal("fetch", vi.fn((url: string) => url.endsWith("/turns") ? turn.promise : Promise.resolve(new Response(new Blob(["audio"])) )));
  await open({ opening: { text: "Mở đầu" }, ttsEnabled: true });
  fireEvent.change(screen.getByLabelText("Câu trả lời của bạn"), { target: { value: "Trả lời" } });
  fireEvent.click(screen.getByRole("button", { name: "Gửi câu trả lời" }));
  act(() => push({ event: "session.question", payload: audioQuestion }));
  await waitFor(() => expect(played).toHaveBeenCalledTimes(1));
  await act(async () => { turn.resolve(ok({ status: "CHALLENGING", question: audioQuestion, questionsAsked: 1, questionsTotal: 3 })); });
  expect(played).toHaveBeenCalledTimes(1);
  expect(screen.getAllByText(audioQuestion.text)).toHaveLength(1);
});
