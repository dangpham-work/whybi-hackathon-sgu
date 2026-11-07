import { ArrowRight, ChevronRight, Network, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { AsyncView, DevelopingBox, ErrorBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { emptyCode, JoinCodeInput, JOIN_CODE_LENGTH } from "../../components/JoinCodeInput";
import { ApiError, apiCall, errorText, type Schema } from "../../lib/api";
import { givenName, useCurrentUser } from "../../lib/auth";
import { NO_TREE, TREE_STATUS } from "../../lib/status";
import { useApi } from "../../lib/useApi";

type ClassOut = Schema<"ClassOut">;

/** Câu lỗi riêng cho tham gia lớp (mã lỗi C2-08 chưa chốt – tra theo mã HTTP, xem PR GD-04). */
function joinError(e: unknown): string {
  if (!(e instanceof ApiError)) return errorText(e);
  if (e.status === 404) return "Không tìm thấy lớp với mã này. Kiểm tra lại mã giảng viên cung cấp.";
  if (e.status === 409) return "Bạn đã ở trong lớp này rồi.";
  if (e.status === 422) return "Mã tham gia gồm đúng 8 chữ hoặc số.";
  if (e.status === 403) return "Chỉ tài khoản sinh viên mới tham gia lớp bằng mã.";
  return e.message;
}

/** SV-01 Danh sách lớp / nhập mã tham gia (Figma 25:482, FR-TB-01, GD-04). Tham gia xong → SV-02 của lớp đó. */
export default function StudentClasses() {
  const navigate = useNavigate();
  const user = useCurrentUser();
  const classes = useApi((signal) => apiCall("get", "/classes", { signal }), []);
  const [code, setCode] = useState(emptyCode);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>();
  const joinCode = code.join("");
  const complete = joinCode.length === JOIN_CODE_LENGTH;

  async function join(e: FormEvent) {
    e.preventDefault();
    if (!complete || busy) return;
    setBusy(true);
    setFailure(undefined);
    try {
      const cls = await apiCall("post", "/classes/join", { body: { joinCode } });
      navigate(`/sv/classes/${cls.id}`);
    } catch (err) {
      setFailure(err);
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-h1 font-bold">Chào {user ? givenName(user.fullName) : "bạn"},</h1>
        <p className="text-body-m text-ink-500">Hôm nay bạn muốn giảng lại khái niệm nào cho Whybi?</p>
      </div>

      <form onSubmit={join} className="space-y-3 rounded-lg border border-honey/50 bg-honey-soft p-4">
        <h2 className="flex items-center gap-2 text-h3 font-semibold text-honey-deep">
          <Plus aria-hidden size={18} /> Tham gia lớp mới
        </h2>
        <p className="text-body-s text-honey-deep">Nhập mã 8 ký tự giảng viên cung cấp</p>
        <JoinCodeInput value={code} onChange={setCode} disabled={busy} />
        {failure !== undefined &&
          (failure instanceof ApiError && failure.notImplemented ? <DevelopingBox text={failure.message} /> : <ErrorBox text={joinError(failure)} />)}
        <Button type="submit" className="w-full py-2.5" disabled={!complete || busy}>
          <ArrowRight aria-hidden size={18} />
          Tham gia lớp
        </Button>
      </form>

      <section className="space-y-2">
        <AsyncView
          state={classes}
          isEmpty={(list) => list.length === 0}
          empty="Bạn chưa tham gia lớp nào. Nhập mã giảng viên cung cấp ở trên để bắt đầu."
        >
          {(list) => (
            <>
              <div className="flex items-center justify-between">
                <h2 className="caps">Lớp của bạn</h2>
                <span className="text-body-s text-ink-500">{list.length} lớp</span>
              </div>
              <ul aria-label="Lớp của bạn" className="space-y-3">
                {list.map((c) => (
                  <li key={c.id}>
                    <ClassCard c={c} />
                  </li>
                ))}
              </ul>
            </>
          )}
        </AsyncView>
      </section>
    </div>
  );
}

function ClassCard({ c }: { c: ClassOut }) {
  // SV chỉ cần biết cây đã mở học chưa: PUBLISHED → "Đã phát hành", còn lại → "Chưa có cây kỹ năng" (màu + biểu tượng từ status.ts)
  const look = c.treeStatus === "PUBLISHED" ? TREE_STATUS.PUBLISHED : NO_TREE;
  const TreeIcon = look.icon;
  return (
    <Link to={`/sv/classes/${c.id}`} className="block rounded-lg border border-line-soft bg-surface p-4 shadow-card hover:border-teal focus-visible:outline-2 focus-visible:outline-teal">
      <div className="flex items-center gap-3">
        <span aria-hidden className="flex size-10 shrink-0 items-center justify-center rounded-md bg-teal-soft text-teal">
          <Network size={20} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-h3 font-semibold">{c.name}</p>
          <p className="truncate text-body-s text-ink-500">
            {c.semester} · {c.studentCount} SV
          </p>
        </div>
        <ChevronRight aria-hidden size={18} className="shrink-0 text-ink-300" />
      </div>
      {/* TODO(GD-06): tiến độ "4/7 nút" theo Figma cần GET /classes/{id}/my-map (C2-10) – ClassOut chưa có */}
      <p className={`mt-3 inline-flex items-center gap-1 rounded-md border px-2 py-1 text-body-s font-semibold ${look.className}`}>
        <TreeIcon aria-hidden size={14} />
        {look === NO_TREE ? "Giảng viên đang chuẩn bị cây kỹ năng" : `Cây kỹ năng ${look.label.toLowerCase()}`}
      </p>
    </Link>
  );
}
