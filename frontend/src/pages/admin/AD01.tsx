import { KeyRound, Lock, LockOpen, Upload, UserPlus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { AdminPage, fieldCls, OneTimePassword, Panel, Td, Th } from "../../components/admin-ui";
import { AsyncView, ErrorBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { apiCall, errorText, type Schema } from "../../lib/api";
import { useApi } from "../../lib/useApi";

type Role = Schema<"Role">;
const ROLE_LABEL: Record<Role, string> = { LECTURER: "Giảng viên", STUDENT: "Sinh viên", ADMIN: "Quản trị viên" };

const ERR: Record<string, string> = {
  USER_EXISTS: "Email hoặc MSSV này đã có tài khoản.",
  VALIDATION_ERROR: "Thông tin chưa hợp lệ – kiểm tra email và MSSV (bắt buộc với sinh viên).",
};

/** AD-01 Tài khoản & nhập CSV (FR-AD-03, GD-15). */
export default function AdminUsers() {
  const [q, setQ] = useState("");
  const [role, setRole] = useState<Role | "">("");
  const users = useApi((signal) => apiCall("get", "/admin/users", { query: { q: q || undefined, role: role || undefined }, signal }), [q, role]);
  const [secret, setSecret] = useState<{ who: string; password: string }>();
  const [failure, setFailure] = useState<string>();
  const [imported, setImported] = useState<Schema<"ImportResult">>();

  const guard = async (fn: () => Promise<void>) => {
    setFailure(undefined);
    try {
      await fn();
    } catch (e) {
      setFailure((e as { code?: string }).code && ERR[(e as { code: string }).code] ? ERR[(e as { code: string }).code] : errorText(e));
    }
  };
  const toggle = (u: Schema<"UserOut">) =>
    guard(async () => {
      await apiCall("patch", "/admin/users/{user_id}", { path: { user_id: u.id }, body: { isActive: !u.isActive } });
      users.reload();
    });
  const reset = (u: Schema<"UserOut">) =>
    guard(async () => {
      const r = await apiCall("post", "/admin/users/{user_id}/reset-password", { path: { user_id: u.id } });
      setSecret({ who: u.fullName, password: r.password });
    });

  return (
    <AdminPage title="Tài khoản & nhập CSV" note="Quản lý tài khoản giảng viên, sinh viên và nhập danh sách sinh viên từ tệp CSV.">
      {failure && <ErrorBox text={failure} />}
      {secret && <OneTimePassword {...secret} />}
      <div className="grid gap-4 xl:grid-cols-2">
        <CreateUser onCreated={(who, password) => { setSecret({ who, password }); users.reload(); }} onFail={setFailure} />
        <ImportCsv onDone={(r) => { setImported(r); users.reload(); }} onFail={setFailure} />
      </div>
      {imported && <ImportReport r={imported} />}
      <Panel title="Danh sách tài khoản">
        <div className="flex flex-wrap gap-2">
          <input aria-label="Tìm tài khoản" placeholder="Tìm theo tên, email, MSSV" className={`${fieldCls} max-w-xs`} value={q} onChange={(e) => setQ(e.target.value)} />
          <select aria-label="Lọc vai trò" className={`${fieldCls} max-w-[12rem]`} value={role} onChange={(e) => setRole(e.target.value as Role | "")}>
            <option value="">Mọi vai trò</option>
            {(Object.keys(ROLE_LABEL) as Role[]).map((r) => (
              <option key={r} value={r}>{ROLE_LABEL[r]}</option>
            ))}
          </select>
        </div>
        <AsyncView state={users} isEmpty={(l) => l.length === 0} empty="Không có tài khoản nào khớp.">
          {(list) => (
            <div className="overflow-x-auto">
              <table aria-label="Tài khoản" className="min-w-full">
                <thead>
                  <tr><Th>Họ tên</Th><Th>Email</Th><Th>MSSV</Th><Th>Vai trò</Th><Th>Trạng thái</Th><Th right>Thao tác</Th></tr>
                </thead>
                <tbody>
                  {list.map((u) => (
                    <tr key={u.id}>
                      <Td strong>{u.fullName}</Td><Td>{u.email}</Td><Td>{u.studentCode ?? "–"}</Td><Td>{ROLE_LABEL[u.role]}</Td>
                      <Td>{u.isActive ? "Đang hoạt động" : "Đã khóa"}</Td>
                      <Td right>
                        <span className="inline-flex gap-1">
                          <button className="rounded-md border border-line-strong p-1.5" aria-label={`${u.isActive ? "Khóa" : "Mở khóa"} ${u.fullName}`} onClick={() => toggle(u)}>
                            {u.isActive ? <Lock aria-hidden size={14} /> : <LockOpen aria-hidden size={14} />}
                          </button>
                          <button className="rounded-md border border-line-strong p-1.5" aria-label={`Đặt lại mật khẩu ${u.fullName}`} onClick={() => reset(u)}>
                            <KeyRound aria-hidden size={14} />
                          </button>
                        </span>
                      </Td>
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

function CreateUser({ onCreated, onFail }: { onCreated: (who: string, pw: string) => void; onFail: (m: string) => void }) {
  const [f, setF] = useState({ fullName: "", email: "", role: "STUDENT" as Role, studentCode: "" });
  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      const r = await apiCall("post", "/admin/users", { body: { ...f, studentCode: f.role === "STUDENT" ? f.studentCode : null } });
      onCreated(r.user.fullName, r.password);
      setF({ fullName: "", email: "", role: "STUDENT", studentCode: "" });
    } catch (err) {
      onFail((err as { code?: string }).code && ERR[(err as { code: string }).code] ? ERR[(err as { code: string }).code] : errorText(err));
    }
  }
  return (
    <Panel title="Tạo tài khoản">
      <form onSubmit={submit} className="grid grid-cols-2 gap-3">
        <label className="col-span-2 space-y-1 text-body-s font-semibold">Họ tên<input required className={fieldCls} value={f.fullName} onChange={(e) => setF({ ...f, fullName: e.target.value })} /></label>
        <label className="space-y-1 text-body-s font-semibold">Email<input required type="email" className={fieldCls} value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></label>
        <label className="space-y-1 text-body-s font-semibold">Vai trò
          <select className={fieldCls} value={f.role} onChange={(e) => setF({ ...f, role: e.target.value as Role })}>
            {(Object.keys(ROLE_LABEL) as Role[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
          </select>
        </label>
        {f.role === "STUDENT" && <label className="col-span-2 space-y-1 text-body-s font-semibold">MSSV<input required className={fieldCls} value={f.studentCode} onChange={(e) => setF({ ...f, studentCode: e.target.value })} /></label>}
        <Button type="submit" className="col-span-2"><UserPlus aria-hidden size={16} /> Tạo tài khoản</Button>
      </form>
    </Panel>
  );
}

function ImportCsv({ onDone, onFail }: { onDone: (r: Schema<"ImportResult">) => void; onFail: (m: string) => void }) {
  const [file, setFile] = useState<File>();
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    try {
      const form = new FormData();
      form.append("file", file);
      onDone(await apiCall("post", "/admin/users/import", { body: form as never }));
    } catch (err) {
      onFail(errorText(err));
    }
  }
  return (
    <Panel title="Nhập sinh viên từ CSV">
      <form onSubmit={submit} className="space-y-3">
        <p className="text-body-s text-ink-500">Tệp CSV UTF-8 với các cột: mssv, ho_ten, email, [khoa]. Tài khoản đã có sẽ được bỏ qua.</p>
        <input type="file" accept=".csv,text/csv" aria-label="Chọn tệp CSV" onChange={(e) => setFile(e.target.files?.[0])} />
        <Button type="submit" disabled={!file}><Upload aria-hidden size={16} /> Nhập danh sách</Button>
      </form>
    </Panel>
  );
}

function ImportReport({ r }: { r: Schema<"ImportResult"> }) {
  return (
    <Panel title="Kết quả nhập CSV">
      <p role="status" className="text-body-m">
        Đã tạo <strong>{r.created.length}</strong> · bỏ qua <strong>{r.skipped.length}</strong> · lỗi <strong>{r.errors.length}</strong>
      </p>
      {r.created.length > 0 && (
        <details>
          <summary className="cursor-pointer font-semibold">Mật khẩu ban đầu (chỉ hiện một lần)</summary>
          <ul className="mt-2 space-y-1 text-body-s">
            {r.created.map((s) => <li key={s.row}>{s.studentCode} – {s.fullName}: <code>{s.password}</code></li>)}
          </ul>
        </details>
      )}
      {[...r.skipped.map((x) => ({ ...x, kind: "Bỏ qua" })), ...r.errors.map((x) => ({ ...x, kind: "Lỗi" }))].map((x) => (
        <p key={`${x.kind}${x.row}`} className="text-body-s text-ink-500">{x.kind} · dòng {x.row}: {x.reason}</p>
      ))}
    </Panel>
  );
}
