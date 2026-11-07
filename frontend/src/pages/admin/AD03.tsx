import { Save } from "lucide-react";
import { useState, type FormEvent } from "react";
import { AdminPage, fieldCls, Panel } from "../../components/admin-ui";
import { ErrorBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { apiCall, errorText, type Schema } from "../../lib/api";

type Config = Schema<"AIConfig">;
type Provider = Schema<"ProviderConfig">;

/** Giá trị gợi ý theo adapter backend (C1-02, C1-12, C1-14): llm gemini|openai_compat, stt fake|whisper|cloud, tts fake|cloud. */
const PROVIDERS = { llm: ["gemini", "openai_compat"], stt: ["fake", "whisper", "cloud"], tts: ["fake", "cloud"] } as const;
const START: Config = {
  llm: { kind: "LLM", provider: "gemini", model: "", fallbackProvider: null, fallbackModel: null, params: {}, quota: {} },
  stt: { kind: "STT", provider: "fake", model: "default", params: {}, quota: {} },
  tts: { kind: "TTS", provider: "fake", model: "default", params: {}, quota: {} },
  audioRetentionDays: 30,
} as Config;
const TITLE = { llm: "Mô hình ngôn ngữ (LLM)", stt: "Nhận dạng giọng nói (STT)", tts: "Đọc câu hỏi (TTS)" } as const;

const ERR: Record<string, string> = {
  INVALID_STT_PROVIDER: "Nhà cung cấp STT không được hỗ trợ.",
  INVALID_TTS_PROVIDER: "Nhà cung cấp TTS không được hỗ trợ.",
  INVALID_PROVIDER_KIND: "Loại nhà cung cấp không khớp.",
};

/**
 * AD-03 Cấu hình nhà cung cấp AI (FR-AD-05, GD-15): đổi model chính / dự phòng không sửa code.
 * Backend chỉ có PUT /admin/ai-config (chưa có GET để đọc cấu hình hiện hành) nên biểu mẫu bắt đầu từ giá trị mặc định.
 */
export default function AdminAiConfig() {
  const [cfg, setCfg] = useState<Config>(START);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [failure, setFailure] = useState<string>();
  const set = (k: "llm" | "stt" | "tts", patch: Partial<Provider>) => setCfg((c) => ({ ...c, [k]: { ...c[k], ...patch } }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setSaved(false);
    setFailure(undefined);
    try {
      await apiCall("put", "/admin/ai-config", { body: cfg });
      setSaved(true);
    } catch (err) {
      const code = (err as { code?: string }).code;
      setFailure((code && ERR[code]) || errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AdminPage title="Cấu hình nhà cung cấp AI" note="Đổi nhà cung cấp và model dự phòng, áp dụng ngay cho các phiên mới.">
      <form onSubmit={submit} className="space-y-4">
        {(["llm", "stt", "tts"] as const).map((k) => (
          <Panel key={k} title={TITLE[k]} label={TITLE[k]}>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1 text-body-s font-semibold">Nhà cung cấp
                <select className={fieldCls} value={cfg[k].provider} onChange={(e) => set(k, { provider: e.target.value })}>
                  {PROVIDERS[k].map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </label>
              <label className="space-y-1 text-body-s font-semibold">Model<input required className={fieldCls} value={cfg[k].model} onChange={(e) => set(k, { model: e.target.value })} /></label>
              {k === "llm" && (
                <>
                  <label className="space-y-1 text-body-s font-semibold">Nhà cung cấp dự phòng
                    <select className={fieldCls} value={cfg.llm.fallbackProvider ?? ""} onChange={(e) => set("llm", { fallbackProvider: e.target.value || null })}>
                      <option value="">Không dùng dự phòng</option>
                      {PROVIDERS.llm.map((p) => <option key={p} value={p}>{p}</option>)}
                    </select>
                  </label>
                  <label className="space-y-1 text-body-s font-semibold">Model dự phòng<input className={fieldCls} value={cfg.llm.fallbackModel ?? ""} onChange={(e) => set("llm", { fallbackModel: e.target.value || null })} /></label>
                </>
              )}
            </div>
          </Panel>
        ))}
        <Panel title="Lưu ghi âm">
          <label className="block max-w-xs space-y-1 text-body-s font-semibold">Số ngày giữ ghi âm
            <input type="number" min={1} className={fieldCls} value={cfg.audioRetentionDays} onChange={(e) => setCfg({ ...cfg, audioRetentionDays: Number(e.target.value) })} />
          </label>
        </Panel>
        {failure && <ErrorBox text={failure} />}
        {saved && <p role="status" className="rounded-md bg-st-pass px-3 py-2 text-body-m text-green-900">Đã lưu cấu hình AI – áp dụng cho phiên mới.</p>}
        <Button type="submit" disabled={busy}><Save aria-hidden size={16} /> Lưu cấu hình</Button>
      </form>
    </AdminPage>
  );
}
