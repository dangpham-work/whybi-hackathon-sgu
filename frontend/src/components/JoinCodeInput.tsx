import { useRef, type ClipboardEvent, type KeyboardEvent } from "react";

export const JOIN_CODE_LENGTH = 8;
/** Mã tham gia: chữ in hoa A–Z và số; bỏ dấu cách, gạch nối và ký tự khác. */
export const cleanCode = (s: string) => s.toUpperCase().replace(/[^A-Z0-9]/g, "");
export const emptyCode = () => Array<string>(JOIN_CODE_LENGTH).fill("");

/**
 * 8 ô nhập mã tham gia (Figma SV-01). Gõ thì tự sang ô sau, Backspace ở ô trống lùi về ô trước,
 * dán / gõ nhiều ký tự một lúc thì tự rải ra các ô. Rộng tối thiểu vừa màn 360 px.
 */
export function JoinCodeInput({ value, onChange, disabled }: { value: string[]; onChange: (v: string[]) => void; disabled?: boolean }) {
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  const focus = (i: number) => refs.current[Math.max(0, Math.min(JOIN_CODE_LENGTH - 1, i))]?.focus();

  const writeFrom = (i: number, text: string) => {
    const next = [...value];
    const chars = cleanCode(text).slice(0, JOIN_CODE_LENGTH - i).split("");
    chars.forEach((c, k) => (next[i + k] = c));
    onChange(next);
    focus(i + chars.length);
  };

  const handleChange = (i: number, raw: string) => {
    let t = cleanCode(raw);
    if (!t) {
      const next = [...value];
      next[i] = "";
      return onChange(next);
    }
    // Ô đã có ký tự mà gõ thêm một ký tự → lấy ký tự mới
    if (t.length === 2 && value[i] && t.startsWith(value[i])) t = t[1];
    writeFrom(i, t);
  };

  const handleKey = (i: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !value[i] && i > 0) {
      e.preventDefault();
      const next = [...value];
      next[i - 1] = "";
      onChange(next);
      focus(i - 1);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      focus(i - 1);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      focus(i + 1);
    }
  };

  const handlePaste = (i: number, e: ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    writeFrom(i, e.clipboardData.getData("text"));
  };

  return (
    <div role="group" aria-label="Mã tham gia 8 ký tự" className="flex gap-1.5">
      {value.map((c, i) => (
        <input
          key={i}
          ref={(el) => {
            refs.current[i] = el;
          }}
          value={c}
          disabled={disabled}
          aria-label={`Ký tự ${i + 1}`}
          inputMode="text"
          autoCapitalize="characters"
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => handleChange(i, e.target.value)}
          onKeyDown={(e) => handleKey(i, e)}
          onPaste={(e) => handlePaste(i, e)}
          onFocus={(e) => e.target.select()}
          className={`h-12 w-0 min-w-0 flex-1 rounded-md border-2 bg-surface text-center text-h2 font-bold uppercase outline-none focus:border-teal disabled:opacity-60 ${
            c ? "border-teal text-ink-900" : "border-line-strong"
          }`}
        />
      ))}
    </div>
  );
}
