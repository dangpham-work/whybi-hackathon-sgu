import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { copyText } from "../lib/classes";

/** Mã tham gia lớp kèm nút chép (GV-01, GV-02). */
export function CopyCode({ code }: { code: string }) {
  const [state, setState] = useState<"idle" | "done" | "fail">("idle");
  async function copy() {
    setState((await copyText(code)) ? "done" : "fail");
    setTimeout(() => setState("idle"), 2000);
  }
  return (
    <span className="inline-flex items-center gap-2">
      <code className="rounded-md bg-app px-2 py-1 font-bold tracking-widest">{code}</code>
      <button type="button" onClick={copy} aria-label={`Chép mã tham gia ${code}`} className="rounded-md p-1.5 text-ink-500 hover:bg-app">
        {state === "done" ? <Check aria-hidden size={16} className="text-teal" /> : <Copy aria-hidden size={16} />}
      </button>
      <span role="status" className="text-body-s text-ink-500">
        {state === "done" ? "Đã chép" : state === "fail" ? "Hãy chép thủ công" : ""}
      </span>
    </span>
  );
}
