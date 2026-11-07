import { ArrowLeft, MailCheck, Send } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { DevelopingBox, ErrorBox } from "../../components/AsyncView";
import { AuthCard, EMAIL_RE, Field } from "../../components/AuthCard";
import { Button } from "../../components/Button";
import { ApiError, apiCall, errorText } from "../../lib/api";

/**
 * AUTH-02 Quên mật khẩu (bổ sung – FR-AD-01, GD-04). Gọi POST /auth/forgot-password {email} (202).
 * Luôn hiện xác nhận trung tính để không lộ email nào có tài khoản.
 */
export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [sentTo, setSentTo] = useState<string>();
  const [failure, setFailure] = useState<unknown>();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setFailure(undefined);
    const value = email.trim();
    if (!EMAIL_RE.test(value)) return setEmailError("Nhập email hợp lệ, ví dụ ten@truong.edu.vn.");
    setEmailError(undefined);
    setBusy(true);
    try {
      await apiCall("post", "/auth/forgot-password", { body: { email: value } });
      setSentTo(value);
    } catch (err) {
      // 404 vẫn coi như đã gửi – không cho dò email
      if (err instanceof ApiError && err.status === 404) setSentTo(value);
      else setFailure(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Quên mật khẩu" subtitle="Nhập email tài khoản, Whybi gửi liên kết đặt lại mật khẩu cho bạn.">
      {sentTo ? (
        <div role="status" className="flex gap-3 rounded-lg border border-teal/40 bg-teal-soft p-4 text-body-m text-teal">
          <MailCheck aria-hidden size={20} className="shrink-0" />
          <p>Nếu {sentTo} có tài khoản, bạn sẽ nhận được email kèm liên kết đặt lại trong vài phút. Nhớ xem cả thư mục Spam.</p>
        </div>
      ) : (
        <form className="space-y-4" onSubmit={submit} noValidate>
          <Field label="Email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} error={emailError} placeholder="ten@truong.edu.vn" />
          {failure !== undefined &&
            (failure instanceof ApiError && failure.notImplemented ? <DevelopingBox text={failure.message} /> : <ErrorBox text={errorText(failure)} />)}
          <Button className="w-full py-2.5" type="submit" disabled={busy}>
            <Send aria-hidden size={18} />
            {busy ? "Đang gửi…" : "Gửi liên kết đặt lại"}
          </Button>
        </form>
      )}
      <Link to="/login" className="mt-4 flex items-center justify-center gap-1 text-body-m font-semibold text-teal hover:underline">
        <ArrowLeft aria-hidden size={16} /> Quay lại đăng nhập
      </Link>
    </AuthCard>
  );
}
