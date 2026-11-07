import { Save } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useParams } from "react-router";
import { AsyncView, ErrorBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { apiCall, ApiError, type Schema } from "../../lib/api";
import { useApi } from "../../lib/useApi";

type Settings = Schema<"ClassSettings">;
const field = "w-full rounded-md border border-line-strong px-3 py-2 text-body-m focus-visible:outline-2 focus-visible:outline-teal";

/** Kiểm trước khi gửi, cùng luật với backend (422): ngưỡng vàng ≤ ngưỡng xanh, số câu phản biện 3–5. Trả null nếu hợp lệ. */
export function checkSettings(s: Settings): string | null {
  if (s.yellowThreshold > s.greenThreshold) return "Ngưỡng vàng không được cao hơn ngưỡng xanh.";
  if (s.challengeCount < 3 || s.challengeCount > 5) return "Số câu phản biện phải từ 3 đến 5.";
  if (s.passThreshold < 0 || s.passThreshold > 100) return "Ngưỡng Đạt phải trong khoảng 0–100.";
  if (s.minSample < 1) return "Cỡ mẫu tối thiểu phải từ 1 trở lên.";
  return null;
}

/** GV-10 Cấu hình ngưỡng (Figma 19:2959, FR-HM-08, GD-14): ngưỡng Đạt, ngưỡng màu bản đồ nhiệt, cỡ mẫu, số câu phản biện. */
export default function LecturerSettings() {
  const { classId = "" } = useParams();
  const settings = useApi((signal) => apiCall("get", "/classes/{class_id}/settings", { path: { class_id: classId }, signal }), [classId]);
  return (
    <div className="space-y-5 p-4 lg:p-7">
      <header>
        <h1 className="text-h1 font-bold">Cấu hình ngưỡng</h1>
        <p className="text-body-m text-ink-500">Thay đổi có hiệu lực ngay: màu bản đồ nhiệt của cả lớp được tính lại.</p>
      </header>
      <AsyncView state={settings}>{(s) => <Form initial={s} classId={classId} />}</AsyncView>
    </div>
  );
}

function Form({ initial, classId }: { initial: Settings; classId: string }) {
  const [s, setS] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [failure, setFailure] = useState<string>();
  const num = (k: keyof Settings, scale = 1) => ({
    value: Math.round(s[k] * scale * 100) / 100,
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => setS({ ...s, [k]: Number(e.target.value) / scale }),
  });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaved(false);
    const problem = checkSettings(s);
    setFailure(problem ?? undefined);
    if (problem) return;
    setBusy(true);
    try {
      setS(await apiCall("put", "/classes/{class_id}/settings", { path: { class_id: classId }, body: s }));
      setSaved(true);
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : "Có lỗi xảy ra, vui lòng thử lại.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="max-w-2xl space-y-4 rounded-lg border border-line-soft bg-surface p-5">
      <label className="block space-y-1 text-body-s font-semibold">
        Ngưỡng Đạt (/100)
        <input type="number" min={0} max={100} className={field} {...num("passThreshold")} />
        <span className="block font-normal text-ink-500">Điểm tối thiểu để một lượt giảng được tính Đạt (BR-03).</span>
      </label>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block space-y-1 text-body-s font-semibold">
          Ngưỡng xanh (% SV Đạt)
          <input type="number" min={1} max={100} className={field} {...num("greenThreshold", 100)} />
          <span className="block font-normal text-ink-500">Từ mức này trở lên là màu xanh.</span>
        </label>
        <label className="block space-y-1 text-body-s font-semibold">
          Ngưỡng vàng (% SV Đạt)
          <input type="number" min={1} max={100} className={field} {...num("yellowThreshold", 100)} />
          <span className="block font-normal text-ink-500">Từ mức này đến ngưỡng xanh là vàng; thấp hơn là đỏ.</span>
        </label>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block space-y-1 text-body-s font-semibold">
          Cỡ mẫu tối thiểu (SV đã thử)
          <input type="number" min={1} className={field} {...num("minSample")} />
          <span className="block font-normal text-ink-500">Chưa đủ mẫu thì nút để xám (FR-HM-04).</span>
        </label>
        <label className="block space-y-1 text-body-s font-semibold">
          Số câu phản biện mỗi phiên (3–5)
          <input type="number" min={3} max={5} className={field} {...num("challengeCount")} />
        </label>
      </div>
      {failure && <ErrorBox text={failure} />}
      {saved && (
        <p role="status" className="rounded-md bg-st-pass px-3 py-2 text-body-m text-green-900">
          Đã lưu cấu hình. Màu bản đồ nhiệt đang được tính lại.
        </p>
      )}
      <Button type="submit" disabled={busy}>
        <Save aria-hidden size={16} /> Lưu cấu hình
      </Button>
    </form>
  );
}
