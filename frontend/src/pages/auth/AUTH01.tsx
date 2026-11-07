import { useState } from "react";
import { Button } from "../../components/Button";
import { Logo } from "../../components/Logo";

/** AUTH-01 Đăng nhập (bổ sung – FR-AD-01). Khung giao diện; nối API POST /auth/login ở thẻ GD-04. */
export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  return (
    <div className="flex min-h-screen items-center justify-center bg-app p-4">
      <form
        className="w-full max-w-sm space-y-4 rounded-lg border border-line-soft bg-surface p-8 shadow-card"
        onSubmit={(e) => e.preventDefault() /* TODO(GD-04): api("/auth/login", …) */}
      >
        <div className="flex items-center gap-3">
          <Logo size={40} />
          <div>
            <h1 className="text-h1 font-bold">Whybi AI</h1>
            <p className="text-body-s text-ink-500">Hỏi “Tại sao” để tri thức nở rộ.</p>
          </div>
        </div>
        <label className="block">
          <span className="caps">Email</span>
          <input className="mt-1 w-full rounded-md border border-line-strong px-3 py-2 outline-teal" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="block">
          <span className="caps">Mật khẩu</span>
          <input className="mt-1 w-full rounded-md border border-line-strong px-3 py-2 outline-teal" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <Button className="w-full" type="submit">
          Đăng nhập
        </Button>
        <a href="/forgot-password" className="block text-center text-body-m font-semibold text-teal">
          Quên mật khẩu?
        </a>
      </form>
    </div>
  );
}
