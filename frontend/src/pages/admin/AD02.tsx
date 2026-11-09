import { Check, CircleCheck, Copy, Pencil, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { AdminPage, fieldCls, Panel, Td, Th } from "../../components/admin-ui";
import { AsyncView, ErrorBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { apiCall, errorText, type Schema } from "../../lib/api";
import { copyText } from "../../lib/classes";
import { useApi } from "../../lib/useApi";

type Course = Schema<"CourseOut">;
const EMPTY = { code: "", name: "", credits: "" as number | "", description: "" };

/** AD-02 Danh mục môn học (FR-AD-04, GD-15). */
export default function AdminCourses() {
  const courses = useApi((signal) => apiCall("get", "/admin/courses", { signal }), []);
  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState<string>();
  const [failure, setFailure] = useState<unknown>();
  const [lastCreated, setLastCreated] = useState<Course>();
  const [copiedId, setCopiedId] = useState<string>();

  async function handleCopy(id: string) {
    await copyText(id);
    setCopiedId(id);
    setTimeout(() => {
      setCopiedId((curr) => (curr === id ? undefined : curr));
    }, 2000);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setFailure(undefined);
    const body = { code: form.code.trim(), name: form.name.trim(), credits: form.credits === "" ? null : form.credits, description: form.description.trim() || null };
    try {
      if (editing) {
        await apiCall("put", "/admin/courses/{course_id}", { path: { course_id: editing }, body });
      } else {
        const created = await apiCall("post", "/admin/courses", { body });
        setLastCreated(created);
      }
      setForm(EMPTY);
      setEditing(undefined);
      courses.reload();
    } catch (err) {
      setFailure(err);
    }
  }
  const edit = (c: Course) => {
    setEditing(c.id);
    setForm({ code: c.code, name: c.name, credits: c.credits ?? "", description: c.description ?? "" });
  };

  return (
    <AdminPage title="Danh mục môn học" note="Môn học để giảng viên mở lớp học phần.">
      {lastCreated && (
        <div role="status" aria-label="Kết quả tạo môn" className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-teal/40 bg-teal-soft p-4 text-body-m text-teal">
          <CircleCheck aria-hidden size={18} className="shrink-0" />
          <p className="flex-1">
            Đã tạo môn <strong>{lastCreated.name}</strong> ({lastCreated.code}). Sao chép mã định danh môn học để giảng viên mở lớp.
          </p>
          <button
            type="button"
            onClick={() => handleCopy(lastCreated.id)}
            aria-label={`Chép mã ${lastCreated.code}`}
            className="inline-flex items-center gap-1.5 rounded-md bg-teal px-3 py-1.5 font-semibold text-white hover:brightness-110"
          >
            {copiedId === lastCreated.id ? <Check aria-hidden size={16} /> : <Copy aria-hidden size={16} />}
            <span>{copiedId === lastCreated.id ? "Đã chép" : "Chép mã môn"}</span>
          </button>
        </div>
      )}
      <Panel title={editing ? "Sửa môn học" : "Thêm môn học"}>
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-4">
          <label className="space-y-1 text-body-s font-semibold">Mã môn<input required className={fieldCls} value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} /></label>
          <label className="space-y-1 text-body-s font-semibold sm:col-span-2">Tên môn<input required className={fieldCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label className="space-y-1 text-body-s font-semibold">Số tín chỉ<input type="number" min={0} max={20} className={fieldCls} value={form.credits} onChange={(e) => setForm({ ...form, credits: e.target.value === "" ? "" : Number(e.target.value) })} /></label>
          <label className="space-y-1 text-body-s font-semibold sm:col-span-4">Mô tả<input className={fieldCls} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
          {failure !== undefined && <div className="sm:col-span-4"><ErrorBox text={errorText(failure)} /></div>}
          <div className="flex gap-2 sm:col-span-4">
            <Button type="submit"><Plus aria-hidden size={16} /> {editing ? "Lưu thay đổi" : "Thêm môn"}</Button>
            {editing && <Button type="button" variant="secondary" onClick={() => { setEditing(undefined); setForm(EMPTY); }}>Hủy sửa</Button>}
          </div>
        </form>
      </Panel>
      <Panel title="Các môn học">
        <AsyncView state={courses} isEmpty={(l) => l.length === 0} empty="Chưa có môn học nào.">
          {(list) => (
            <table aria-label="Môn học" className="min-w-full">
              <thead><tr><Th>Mã</Th><Th>Tên môn</Th><Th right>Tín chỉ</Th><Th right>Thao tác</Th></tr></thead>
              <tbody>
                {list.map((c) => (
                  <tr key={c.id}>
                    <Td strong>{c.code}</Td><Td>{c.name}</Td><Td right>{c.credits ?? "–"}</Td>
                    <Td right>
                      <div className="inline-flex items-center justify-end gap-1.5">
                        <button
                          type="button"
                          onClick={() => handleCopy(c.id)}
                          title="Sao chép mã môn học để giảng viên tạo lớp"
                          aria-label={`Chép mã môn ${c.code}`}
                          className="rounded-md border border-line-strong p-1.5 text-ink-500 hover:bg-app hover:text-ink-900"
                        >
                          {copiedId === c.id ? <Check aria-hidden size={14} className="text-teal" /> : <Copy aria-hidden size={14} />}
                        </button>
                        <button aria-label={`Sửa ${c.code}`} className="rounded-md border border-line-strong p-1.5 hover:bg-app" onClick={() => edit(c)}><Pencil aria-hidden size={14} /></button>
                      </div>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </AsyncView>
      </Panel>
    </AdminPage>
  );
}
