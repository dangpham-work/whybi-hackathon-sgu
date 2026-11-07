import { Save } from "lucide-react";
import { useState, type FormEvent } from "react";
import { AdminPage, fieldCls, Panel, Td, Th } from "../../components/admin-ui";
import { AsyncView, ErrorBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { apiCall, errorText } from "../../lib/api";
import { useApi } from "../../lib/useApi";

const num = (v: number | null | undefined) => (v == null ? "Không giới hạn" : v.toLocaleString("vi-VN"));
const toNum = (s: string) => (s.trim() === "" ? null : Number(s));

/** AD-04 Hạn mức token / phút ghi âm theo lớp hoặc SV (FR-AD-06, GD-15). Vượt hạn mức, backend trả 429 QUOTA_EXCEEDED. */
export default function AdminQuotas() {
  const quotas = useApi((signal) => apiCall("get", "/admin/quotas", { signal }), []);
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
  const pick = (q: { scope: "CLASS" | "STUDENT"; scopeId: string; tokenLimit?: number | null; audioMinutesLimit?: number | null }) =>
    setF({ scope: q.scope, scopeId: q.scopeId, tokens: q.tokenLimit?.toString() ?? "", minutes: q.audioMinutesLimit?.toString() ?? "" });

  return (
    <AdminPage title="Hạn mức" note="Giới hạn token LLM và số phút ghi âm cho từng lớp hoặc sinh viên để kiểm soát chi phí.">
      <Panel title="Đặt hạn mức">
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-4">
          <label className="space-y-1 text-body-s font-semibold">Phạm vi
            <select className={fieldCls} value={f.scope} onChange={(e) => setF({ ...f, scope: e.target.value as "CLASS" | "STUDENT" })}>
              <option value="CLASS">Lớp</option>
              <option value="STUDENT">Sinh viên</option>
            </select>
          </label>
          <label className="space-y-1 text-body-s font-semibold sm:col-span-3">Mã định danh lớp / SV (UUID)<input required className={fieldCls} value={f.scopeId} onChange={(e) => setF({ ...f, scopeId: e.target.value })} /></label>
          <label className="space-y-1 text-body-s font-semibold sm:col-span-2">Giới hạn token (để trống = không giới hạn)<input type="number" min={0} className={fieldCls} value={f.tokens} onChange={(e) => setF({ ...f, tokens: e.target.value })} /></label>
          <label className="space-y-1 text-body-s font-semibold sm:col-span-2">Giới hạn phút ghi âm<input type="number" min={0} className={fieldCls} value={f.minutes} onChange={(e) => setF({ ...f, minutes: e.target.value })} /></label>
          {failure !== undefined && <div className="sm:col-span-4"><ErrorBox text={errorText(failure)} /></div>}
          <div className="sm:col-span-4"><Button type="submit"><Save aria-hidden size={16} /> Lưu hạn mức</Button></div>
        </form>
      </Panel>
      <Panel title="Hạn mức đã đặt">
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
    </AdminPage>
  );
}
