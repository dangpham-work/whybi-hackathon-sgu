import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { UnifiedChatComposer } from "../components/UnifiedChatComposer";

class FakeSpeechRecognition {
  continuous = true;
  interimResults = true;
  lang = "vi-VN";
  start = vi.fn();
  stop = vi.fn();
  abort = vi.fn();
  onresult: ((e: unknown) => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  onend: (() => void) | null = null;
  static instance: FakeSpeechRecognition | null = null;
  constructor() {
    FakeSpeechRecognition.instance = this;
  }
}

describe("UnifiedChatComposer (Thanh chat gộp MX2)", () => {
  beforeEach(() => {
    vi.stubGlobal("SpeechRecognition", FakeSpeechRecognition);
    vi.stubGlobal("webkitSpeechRecognition", FakeSpeechRecognition);
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi.fn(async () => ({
          getTracks: () => [{ stop: vi.fn() }],
        })),
      },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("hiển thị đúng bố cục: thời gian / 1p30s, mic, waveform ở giữa, số ký tự và nút gửi", () => {
    render(
      <UnifiedChatComposer
        turnType="ANSWER"
        maxSeconds={90}
        consented={true}
        onConsent={vi.fn()}
        busy={false}
        onSend={vi.fn()}
      />
    );

    // Thời gian hiển thị 00:00 / 01:30
    expect(screen.getByText("00:00 / 01:30")).toBeTruthy();

    // Nút micro
    expect(screen.getByRole("button", { name: "Bắt đầu ghi âm" })).toBeTruthy();

    // Thanh âm lượng dạng sóng (Waveform)
    expect(screen.getByRole("img", { name: /Dạng sóng âm thanh/ })).toBeTruthy();

    // Bộ đếm ký tự
    expect(screen.getByText(/0 \/ 20\.000/)).toBeTruthy();

    // Textarea trả lời
    expect(screen.getByRole("textbox", { name: "Câu trả lời của bạn" })).toBeTruthy();

    // Nút gửi
    expect(screen.getByRole("button", { name: "Gửi câu trả lời" })).toBeTruthy();
  });

  it("nhấn Enter gửi tin nhắn, Shift + Enter xuống dòng mà không gửi", async () => {
    const onSend = vi.fn(async () => {});
    render(
      <UnifiedChatComposer
        turnType="ANSWER"
        maxSeconds={90}
        consented={true}
        onConsent={vi.fn()}
        busy={false}
        onSend={onSend}
      />
    );

    const textarea = screen.getByRole("textbox", { name: "Câu trả lời của bạn" });
    await act(async () => {
      fireEvent.change(textarea, { target: { value: "Đây là câu trả lời" } });
    });

    // Shift + Enter: không gửi
    await act(async () => {
      fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    });
    expect(onSend).not.toHaveBeenCalled();

    // Enter: gửi tin nhắn
    await act(async () => {
      fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    });
    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith(
      expect.objectContaining({
        text: "Đây là câu trả lời",
        inputMode: "TEXT",
      })
    );
  });

  it("khi ghi âm tới đâu thì text chạy vào ô tới đó; chỉnh sửa và ghi âm tiếp thì text mới gắn nối tiếp vào text cũ", async () => {
    const onSend = vi.fn(async () => {});
    render(
      <UnifiedChatComposer
        turnType="EXPLANATION"
        maxSeconds={300}
        consented={true}
        onConsent={vi.fn()}
        busy={false}
        onSend={onSend}
      />
    );

    const micBtn = screen.getByRole("button", { name: "Bắt đầu ghi âm" });
    await act(async () => {
      fireEvent.click(micBtn);
    });

    const sr = FakeSpeechRecognition.instance;
    expect(sr).toBeTruthy();

    // Mô phỏng giọng nói stream kết quả vào ô chat
    act(() => {
      sr?.onresult?.({
        results: [
          Object.assign([{ transcript: "Khái niệm con trỏ", confidence: 0.95 }], { isFinal: true }),
        ],
      });
    });

    const textarea = screen.getByRole("textbox", { name: "Lời giảng của bạn" }) as HTMLTextAreaElement;
    expect(textarea.value).toBe("Khái niệm con trỏ");

    // Dừng ghi âm
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Dừng ghi âm" }));
    });

    // Người dùng bấm chuột vào chỉnh sửa trực tiếp trên ô text
    fireEvent.change(textarea, { target: { value: "Khái niệm con trỏ trong ngôn ngữ C" } });
    expect(textarea.value).toBe("Khái niệm con trỏ trong ngôn ngữ C");

    // Bấm ghi âm tiếp lần 2
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Bắt đầu ghi âm" }));
    });

    const sr2 = FakeSpeechRecognition.instance;
    act(() => {
      sr2?.onresult?.({
        results: [
          Object.assign([{ transcript: "dùng để lưu địa chỉ ô nhớ", confidence: 0.95 }], { isFinal: true }),
        ],
      });
    });

    // Text mới được gắn nối tiếp vào sau text cũ đã chỉnh sửa
    expect(textarea.value).toBe("Khái niệm con trỏ trong ngôn ngữ C dùng để lưu địa chỉ ô nhớ");

    // Dừng ghi âm lần 2
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Dừng ghi âm" }));
    });

    // Bấm nút gửi
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Gửi/ }));
    });

    expect(onSend).toHaveBeenCalledWith(
      expect.objectContaining({
        text: "Khái niệm con trỏ trong ngôn ngữ C dùng để lưu địa chỉ ô nhớ",
        inputMode: "VOICE",
      })
    );
  });
});
