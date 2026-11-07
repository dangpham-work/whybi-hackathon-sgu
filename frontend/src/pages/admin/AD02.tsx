import { Pencil, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { AdminPage, fieldCls, Panel, Td, Th } from "../../components/admin-ui";
import { AsyncView, ErrorBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { apiCall, errorText, type Schema } from "../../lib/api";
import { useApi } from "../../lib/useApi";

type Course = Schema<"CourseOut">;
const EMPTY = { code: "", name: "", credits: "" as number | "", description: "" };

/** AD-02 Danh mục môn học (FR-AD-04, GD-15). */
export default function AdminCourses() {
  const courses = useApi((signal) => apiCall("get", "/admin/courses", { signal }), []);
  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState<string>();
  const [failure, setFailure] = useState<unknown>();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setFailure(undefined);
    const body = { code: form.code.trim(), name: form.name.trim(), credits: form.credits === "" ? null : form.credits, description: form.description.trim() || null };
    try {
      if (editing) await apiCall("put", "/admin/courses/{course_id}", { path: { course_id: editing }, body });
      else await apiCall("post", "/admin/courses", { body });
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
              <thead><tr><Th>Mã</Th><Th>Tên môn</Th><Th right>Tín chỉ</Th><Th right>Sửa</Th></tr></thead>
              <tbody>
                {list.map((c) => (
                  <tr key={c.id}>
                    <Td strong>{c.code}</Td><Td>{c.name}</Td><Td right>{c.credits ?? "–"}</Td>
                    <Td right><button aria-label={`Sửa ${c.code}`} className="rounded-md border border-line-strong p-1.5" onClick={() => edit(c)}><Pencil aria-hidden size={14} /></button></Td>
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
