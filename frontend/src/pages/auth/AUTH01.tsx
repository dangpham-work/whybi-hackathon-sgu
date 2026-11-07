import { Eye, EyeOff, LogIn } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { DevelopingBox, ErrorBox } from "../../components/AsyncView";
import { AuthCard, EMAIL_RE, Field } from "../../components/AuthCard";
import { Button } from "../../components/Button";
import { ApiError, errorText } from "../../lib/api";
import { auth, homeFor, safeNext } from "../../lib/auth";

/** Câu lỗi riêng cho màn đăng nhập: ở đây 401 nghĩa là sai thông tin, không phải "phiên hết hạn". */
function loginError(e: unknown): string {
  if (e instanceof ApiError && (e.status === 401 || e.code === "INVALID_CREDENTIALS")) return "Email hoặc mật khẩu không đúng.";
  if (e instanceof ApiError && e.status === 423) return "Tài khoản tạm khóa do đăng nhập sai nhiều lần. Thử lại sau ít phút.";
  return errorText(e);
}

/** AUTH-01 Đăng nhập (bổ sung – FR-AD-01, GD-04). Thành công → màn đầu theo vai (sơ đồ 5.5.1) hoặc ?next=. */
export default function Login() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [emailError, setEmailError] = useState<string>();
  const [failure, setFailure] = useState<unknown>();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setFailure(undefined);
    if (!EMAIL_RE.test(email.trim())) return setEmailError("Nhập email hợp lệ, ví dụ ten@truong.edu.vn.");
    setEmailError(undefined);
    setBusy(true);
    try {
      const me = await auth.login(email.trim(), password);
      navigate(safeNext(params.get("next")) ?? homeFor(me.role), { replace: true });
    } catch (err) {
      setFailure(err);
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Đăng nhập" subtitle="Dùng tài khoản trường cấp cho bạn.">
      <form className="space-y-4" onSubmit={submit} noValidate>
        <Field label="Email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} error={emailError} placeholder="ten@truong.edu.vn" />
        <Field
          label="Mật khẩu"
          type={show ? "text" : "password"}
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          trailing={
            // Nhãn cố ý không chứa "Mật khẩu" để getByLabel("Mật khẩu") (e2e SMOKE-04) chỉ trúng ô nhập
            <button type="button" className="px-3 text-ink-500 hover:text-ink-900" aria-label="Hiện ký tự đã nhập" aria-pressed={show} onClick={() => setShow((s) => !s)}>
              {show ? <EyeOff aria-hidden size={18} /> : <Eye aria-hidden size={18} />}
            </button>
          }
        />
        {failure !== undefined &&
          (failure instanceof ApiError && failure.notImplemented ? <DevelopingBox text={failure.message} /> : <ErrorBox text={loginError(failure)} />)}
        <Button className="w-full py-2.5" type="submit" disabled={busy || !password}>
          <LogIn aria-hidden size={18} />
          {busy ? "Đang đăng nhập…" : "Đăng nhập"}
        </Button>
        <Link to="/forgot-password" className="block text-center text-body-m font-semibold text-teal hover:underline">
          Quên mật khẩu?
        </Link>
      </form>
    </AuthCard>
  );
}
