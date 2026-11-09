import { Gauge, Save } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { AdminPage, fieldCls, Panel, Td, Th } from "../../components/admin-ui";
import { AsyncView, ErrorBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { apiCall, errorText, type Schema } from "../../lib/api";
import { useApi } from "../../lib/useApi";

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

const num = (v: number | null | undefined) => (v == null ? "Không giới hạn" : v.toLocaleString("vi-VN"));
const toNum = (s: string) => (s.trim() === "" ? null : Number(s));

type ClassLite = { id: string; name: string };
type StudentLite = { id: string; fullName: string; studentCode: string | null };
type UsageStat = { provider: string; model: string; tokensUsed: number; audioMinutesUsed: number; sessionCount: number };
type QuotaRow = { scope: "CLASS" | "STUDENT"; scopeId: string; tokenLimit?: number | null; audioMinutesLimit?: number | null; name?: string | null; tokensUsed: number; audioMinutesUsed: number };

/**
 * AD-03 Cấu hình AI + AD-04 Hạn mức (FR-AD-05, FR-AD-06, GD-15), gộp một trang cho gọn (C2-24):
 * đổi model chính / dự phòng, xem token đã dùng theo provider/model, và đặt hạn mức theo lớp / SV
 * bằng danh sách chọn thay vì gõ tay UUID.
 */
export default function AdminAiConfig() {
  const [cfg, setCfg] = useState<Config>(START);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [failure, setFailure] = useState<string>();
  const set = (k: "llm" | "stt" | "tts", patch: Partial<Provider>) => setCfg((c) => ({ ...c, [k]: { ...c[k], ...patch } }));

  useEffect(() => {
    let active = true;
    apiCall("get", "/admin/ai-config" as any)
      .then((c) => {
        if (active && c) setCfg(c as Config);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

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
    <AdminPage title="Cấu hình nhà cung cấp AI" note="Đổi nhà cung cấp, model dự phòng, xem mức token đã dùng và đặt hạn mức theo lớp / sinh viên.">
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

      <UsageStats />
      <Quotas />
    </AdminPage>
  );
}

function UsageStats() {
  const stats = useApi((signal) => apiCall("get", "/admin/usage-stats" as any, { signal }) as Promise<UsageStat[]>, []);
  return (
    <Panel title="Token đã dùng theo nhà cung cấp & model" label="Token đã dùng theo nhà cung cấp & model">
      <AsyncView state={stats} isEmpty={(l) => l.length === 0} empty="Chưa có lượt dùng AI nào được ghi nhận.">
        {(list) => (
          <div className="overflow-x-auto">
            <table aria-label="Thống kê token" className="min-w-full">
              <thead><tr><Th>Nhà cung cấp</Th><Th>Model</Th><Th right>Token đã dùng</Th><Th right>Phút ghi âm</Th><Th right>Số phiên</Th></tr></thead>
              <tbody>
                {list.map((s) => (
                  <tr key={`${s.provider}${s.model}`}>
                    <Td strong>{s.provider}</Td><Td>{s.model}</Td>
                    <Td right>{s.tokensUsed.toLocaleString("vi-VN")}</Td>
                    <Td right>{s.audioMinutesUsed.toFixed(1).replace(".", ",")}</Td>
                    <Td right>{s.sessionCount}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </AsyncView>
    </Panel>
  );
}

/** AD-04 Hạn mức token / phút ghi âm theo lớp hoặc SV (FR-AD-06). Chọn lớp / SV bằng danh sách, không gõ tay UUID. */
function Quotas() {
  const quotas = useApi((signal) => apiCall("get", "/admin/quotas", { signal }), []);
  const classes = useApi((signal) => apiCall("get", "/admin/classes-lite" as any, { signal }) as Promise<ClassLite[]>, []);
  const students = useApi((signal) => apiCall("get", "/admin/users", { query: { role: "STUDENT" }, signal }) as Promise<StudentLite[]>, []);
  const [f, setF] = useState({ scope: "CLASS" as "CLASS" | "STUDENT", scopeId: "", tokens: "", minutes: "" });
  const [failure, setFailure] = useState<unknown>();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setFailure(undefined);
    try {
      await apiCall("put", "/admin/quotas", { body: { scope: f.scope, scopeId: f.scopeId.trim(), tokenLimit: toNum(f.tokens), audioMinutesLimit: toNum(f.minutes) } });
      setF({ ...f, scopeId: "", tokens: "", minutes: "" });
      quotas.reload();
    } catch (err) {
      setFailure(err);
    }
  }
  const pick = (q: QuotaRow) =>
    setF({ scope: q.scope, scopeId: q.scopeId, tokens: q.tokenLimit?.toString() ?? "", minutes: q.audioMinutesLimit?.toString() ?? "" });

  const options =
    f.scope === "CLASS"
      ? (classes.data ?? []).map((c) => ({ id: c.id, label: c.name }))
      : (students.data ?? []).map((s) => ({ id: s.id, label: s.studentCode ? `${s.studentCode} – ${s.fullName}` : s.fullName }));

  return (
    <Panel title="Hạn mức theo lớp / sinh viên" label="Hạn mức theo lớp / sinh viên">
      <p className="text-body-s text-ink-500">Giới hạn token LLM và số phút ghi âm cho từng lớp hoặc sinh viên để kiểm soát chi phí.</p>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-4">
        <label className="space-y-1 text-body-s font-semibold">Phạm vi
          <select className={fieldCls} value={f.scope} onChange={(e) => setF({ ...f, scope: e.target.value as "CLASS" | "STUDENT", scopeId: "" })}>
            <option value="CLASS">Lớp</option>
            <option value="STUDENT">Sinh viên</option>
          </select>
        </label>
        <label className="space-y-1 text-body-s font-semibold sm:col-span-3">{f.scope === "CLASS" ? "Lớp" : "Sinh viên"}
          <select required className={fieldCls} value={f.scopeId} onChange={(e) => setF({ ...f, scopeId: e.target.value })}>
            <option value="">— Chọn —</option>
            {options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
          </select>
        </label>
        <label className="space-y-1 text-body-s font-semibold sm:col-span-2">Giới hạn token (để trống = không giới hạn)<input type="number" min={0} className={fieldCls} value={f.tokens} onChange={(e) => setF({ ...f, tokens: e.target.value })} /></label>
        <label className="space-y-1 text-body-s font-semibold sm:col-span-2">Giới hạn phút ghi âm<input type="number" min={0} className={fieldCls} value={f.minutes} onChange={(e) => setF({ ...f, minutes: e.target.value })} /></label>
        {failure !== undefined && <div className="sm:col-span-4"><ErrorBox text={errorText(failure)} /></div>}
        <div className="sm:col-span-4"><Button type="submit"><Gauge aria-hidden size={16} /> Lưu hạn mức</Button></div>
      </form>
      <AsyncView state={quotas} isEmpty={(l) => l.length === 0} empty="Chưa đặt hạn mức nào – hiện không giới hạn.">
        {(list) => (
          <div className="overflow-x-auto">
            <table aria-label="Hạn mức" className="min-w-full">
              <thead><tr><Th>Đối tượng</Th><Th>Phạm vi</Th><Th right>Token đã dùng / hạn</Th><Th right>Phút ghi âm đã dùng / hạn</Th><Th right>Sửa</Th></tr></thead>
              <tbody>
                {list.map((q) => (
                  <tr key={`${q.scope}${q.scopeId}`}>
                    <Td strong>{q.name ?? q.scopeId}</Td><Td>{q.scope === "CLASS" ? "Lớp" : "Sinh viên"}</Td>
                    <Td right>{q.tokensUsed.toLocaleString("vi-VN")} / {num(q.tokenLimit)}</Td>
                    <Td right>{q.audioMinutesUsed.toFixed(1).replace(".", ",")} / {num(q.audioMinutesLimit)}</Td>
                    <Td right><button className="rounded-md border border-line-strong px-2 py-1 text-body-s" aria-label={`Sửa hạn mức ${q.name ?? q.scopeId}`} onClick={() => pick(q)}>Sửa</button></Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </AsyncView>
    </Panel>
  );
}
