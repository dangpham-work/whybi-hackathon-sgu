import { Check } from "lucide-react";
import { useState } from "react";
import { AdminPage, Panel, Td, Th } from "../../components/admin-ui";
import { AsyncView, ErrorBox } from "../../components/AsyncView";
import { apiCall, errorText } from "../../lib/api";
import { FLAG_LABEL } from "../../lib/criteria";
import { useApi } from "../../lib/useApi";

const vn = (iso: string) => new Date(iso).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const SEVERITY: Record<string, string> = { LOW: "Thấp", MEDIUM: "Trung bình", HIGH: "Cao" };

/** AD-05 Nhật ký & cờ vi phạm (FR-AD-07, GD-15). */
export default function AdminFlags() {
  const [resolved, setResolved] = useState(false);
  const flags = useApi((signal) => apiCall("get", "/admin/flags", { query: { resolved }, signal }), [resolved]);
  const logs = useApi((signal) => apiCall("get", "/admin/audit-logs", { query: { limit: 50 }, signal }), []);
  const [failure, setFailure] = useState<unknown>();

  async function resolve(id: string) {
    setFailure(undefined);
    try {
      await apiCall("post", "/admin/flags/{flag_id}/resolve", { path: { flag_id: id } });
      flags.reload();
      logs.reload();
    } catch (e) {
      setFailure(e);
    }
  }

  return (
    <AdminPage title="Nhật ký & cờ vi phạm" note="Cờ vi phạm do hệ thống gắn khi phiên có dấu hiệu bất thường, và nhật ký thao tác quản trị.">
      {failure !== undefined && <ErrorBox text={errorText(failure)} />}
      <Panel title="Cờ vi phạm">
        <div role="tablist" aria-label="Trạng thái cờ" className="inline-flex gap-1 rounded-lg bg-app p-1">
          {([[false, "Chưa xử lý"], [true, "Đã xử lý"]] as const).map(([v, label]) => (
            <button key={label} role="tab" aria-selected={resolved === v} onClick={() => setResolved(v)} className={`rounded-md px-4 py-1.5 text-body-m font-semibold ${resolved === v ? "bg-surface shadow-card" : "text-ink-500"}`}>{label}</button>
          ))}
        </div>
        <AsyncView state={flags} isEmpty={(l) => l.length === 0} empty={resolved ? "Chưa có cờ nào được xử lý." : "Không có cờ nào cần xử lý."}>
          {(list) => (
            <div className="overflow-x-auto">
              <table aria-label="Cờ vi phạm" className="min-w-full">
                <thead><tr><Th>Thời gian</Th><Th>Sinh viên</Th><Th>Loại</Th><Th>Mức độ</Th><Th>Chi tiết</Th><Th right>Xử lý</Th></tr></thead>
                <tbody>
                  {list.map((f) => (
                    <tr key={f.id}>
                      <Td>{vn(f.createdAt)}</Td><Td strong>{f.studentName}</Td>
                      <Td>{FLAG_LABEL[f.type as keyof typeof FLAG_LABEL] ?? f.type}</Td><Td>{SEVERITY[f.severity] ?? f.severity}</Td><Td>{f.detail ?? "–"}</Td>
                      <Td right>
                        {f.resolved ? "Đã xử lý" : (
                          <button className="inline-flex items-center gap-1 rounded-md border border-line-strong px-2 py-1 text-body-s font-semibold" aria-label={`Đánh dấu đã xử lý cờ của ${f.studentName}`} onClick={() => resolve(f.id)}>
                            <Check aria-hidden size={14} /> Đã xử lý
                          </button>
                        )}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </AsyncView>
      </Panel>
      <Panel title="Nhật ký thao tác">
        <AsyncView state={logs} isEmpty={(l) => l.length === 0} empty="Chưa có thao tác nào được ghi.">
          {(list) => (
            <table aria-label="Nhật ký thao tác" className="min-w-full">
              <thead><tr><Th>Thời gian</Th><Th>Thao tác</Th><Th>Đối tượng</Th></tr></thead>
              <tbody>
                {list.map((l) => <tr key={l.id}><Td>{vn(l.createdAt)}</Td><Td strong>{l.action}</Td><Td>{l.entity}</Td></tr>)}
              </tbody>
            </table>
          )}
        </AsyncView>
      </Panel>
    </AdminPage>
  );
}
