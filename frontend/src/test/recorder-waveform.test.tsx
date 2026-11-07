import { act, fireEvent, render, screen } from "@testing-library/react";
import { Recorder } from "../components/Recorder";
import { Waveform } from "../components/Waveform";

const originalMediaDevices = Object.getOwnPropertyDescriptor(navigator, "mediaDevices");
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  if (originalMediaDevices) Object.defineProperty(navigator, "mediaDevices", originalMediaDevices);
  else Reflect.deleteProperty(navigator, "mediaDevices");
});

it("đóng AudioContext nếu dựng đồ thị dạng sóng thất bại", () => {
  const close = vi.fn(async () => undefined);
  vi.stubGlobal("AudioContext", class {
    close = close;
    createAnalyser() { throw new Error("không dựng được analyser"); }
  });
  render(<Waveform stream={{} as MediaStream} active />);
  expect(close).toHaveBeenCalledOnce();
});

// stop() đổi state ngay, dataavailable/onstop chỉ được trình duyệt phát ở tác vụ sau.
class AsyncRecorder {
  static instances: AsyncRecorder[] = [];
  static isTypeSupported = () => true;
  state = "inactive";
  mimeType = "audio/webm";
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor(public stream: MediaStream) { AsyncRecorder.instances.push(this); }
  start() { this.state = "recording"; }
  stop = vi.fn(() => { this.state = "inactive"; });
  finishStop() {
    this.ondataavailable?.({ data: new Blob(["final-audio"]) });
    this.onstop?.();
  }
}

function setupRecorder(onSubmit = vi.fn(async (_blob: Blob, _ms: number): Promise<void> => undefined)) {
  AsyncRecorder.instances = [];
  vi.stubGlobal("MediaRecorder", AsyncRecorder);
  const stopTrack = vi.fn();
  const stream = { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream;
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn(async () => stream) },
  });
  const view = render(<Recorder consented onConsent={vi.fn()} onSubmit={onSubmit} onUseText={vi.fn()} />);
  return { ...view, onSubmit, stopTrack };
}

it("Gửi chờ onstop bất đồng bộ và khóa Ghi lại/Gửi trong lúc chờ lẫn lúc gửi", async () => {
  let complete!: () => void;
  const onSubmit = vi.fn((_blob: Blob, _ms: number) => new Promise<void>((resolve) => { complete = resolve; }));
  setupRecorder(onSubmit);
  fireEvent.click(screen.getByRole("button", { name: "Bắt đầu ghi âm" }));
  await screen.findByText("Đang ghi");
  const rec = AsyncRecorder.instances[0];
  fireEvent.click(screen.getByRole("button", { name: "Gửi bản ghi" }));
  expect(onSubmit).not.toHaveBeenCalled();
  expect((screen.getByRole("button", { name: "Ghi lại" }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole("button", { name: "Gửi bản ghi" }) as HTMLButtonElement).disabled).toBe(true);
  act(() => rec.finishStop());
  expect(onSubmit).toHaveBeenCalledOnce();
  expect(onSubmit.mock.calls[0][0].size).toBe(new Blob(["final-audio"]).size);
  fireEvent.click(screen.getByRole("button", { name: "Ghi lại" }));
  fireEvent.click(screen.getByRole("button", { name: "Gửi bản ghi" }));
  expect(onSubmit).toHaveBeenCalledOnce();
  await act(async () => complete());
  expect((screen.getByRole("button", { name: "Bắt đầu ghi âm" }) as HTMLButtonElement).disabled).toBe(false);
});

it("Ghi lại sau Dừng hủy callback cũ và trả micro trước onstop", async () => {
  const { stopTrack, onSubmit } = setupRecorder();
  fireEvent.click(screen.getByRole("button", { name: "Bắt đầu ghi âm" }));
  await screen.findByText("Đang ghi");
  const old = AsyncRecorder.instances[0];
  fireEvent.click(screen.getByRole("button", { name: "Dừng ghi âm" }));
  fireEvent.click(screen.getByRole("button", { name: "Ghi lại" }));
  expect(stopTrack).toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Bắt đầu ghi âm" }));
  await screen.findByText("Đang ghi");
  act(() => old.finishStop());
  expect(screen.getByText("Đang ghi")).toBeTruthy();
  expect(onSubmit).not.toHaveBeenCalled();
});

it.each(["recording", "stopping", "sending"])("unmount khi %s trả micro và không gửi thêm", async (phase) => {
  let complete!: () => void;
  const onSubmit = vi.fn((_blob: Blob, _ms: number) => new Promise<void>((resolve) => { complete = resolve; }));
  const { unmount, stopTrack } = setupRecorder(onSubmit);
  fireEvent.click(screen.getByRole("button", { name: "Bắt đầu ghi âm" }));
  await screen.findByText("Đang ghi");
  const rec = AsyncRecorder.instances[0];
  if (phase !== "recording") fireEvent.click(screen.getByRole("button", { name: "Gửi bản ghi" }));
  if (phase === "sending") act(() => rec.finishStop());
  unmount();
  expect(stopTrack).toHaveBeenCalled();
  act(() => rec.finishStop());
  expect(onSubmit).toHaveBeenCalledTimes(phase === "sending" ? 1 : 0);
  if (phase === "sending") await act(async () => complete());
});

it("trả micro và báo lỗi khi MediaRecorder.start thất bại", async () => {
  const { stopTrack, onSubmit } = setupRecorder();
  vi.spyOn(AsyncRecorder.prototype, "start").mockImplementationOnce(() => { throw new Error("start failed"); });
  fireEvent.click(screen.getByRole("button", { name: "Bắt đầu ghi âm" }));
  expect((await screen.findByRole("alert")).textContent).toContain("Không mở được micro");
  expect(stopTrack).toHaveBeenCalled();
  expect(onSubmit).not.toHaveBeenCalled();
});
