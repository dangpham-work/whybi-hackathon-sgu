import { ArrowLeft, LogOut, Mail, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { AsyncView, EmptyBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { Logo } from "../../components/Logo";
import { apiCall, getToken } from "../../lib/api";
import { auth, homeFor, ROLE_LABEL, type Me } from "../../lib/auth";
import { useApi } from "../../lib/useApi";
import { Avatar } from "../../layouts/shell";

/**
 * ME-01 Hồ sơ cá nhân (FR-AD-01, GD-04): tên, email, vai trò, đăng xuất.
 * Sửa hồ sơ chờ C2-07 chốt body của PATCH /me (OpenAPI hiện chưa có) – xem PR GD-04.
 */
export default function Profile() {
  const navigate = useNavigate();
  const [leaving, setLeaving] = useState(false);
  const me = useApi<Me | null>(async (signal) => {
    if (!getToken()) return null;
    const u = await apiCall("get", "/me", { signal });
    return u;
  }, []);

  async function logout() {
    setLeaving(true);
    await auth.logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen bg-app">
      <header className="flex items-center gap-3 border-b border-line-soft bg-surface px-4 py-3">
        <Logo size={32} />
        <p className="text-h3 font-bold">Hồ sơ cá nhân</p>
      </header>
      <main className="mx-auto max-w-md space-y-4 p-4">
        <AsyncView state={me}>
          {(u) =>
            u ? (
              <>
                <section className="flex items-center gap-4 rounded-lg border border-line-soft bg-surface p-5 shadow-card">
                  <Avatar name={u.fullName} />
                  <div className="min-w-0">
                    <h1 className="truncate text-h2 font-bold">{u.fullName}</h1>
                    <p className="flex items-center gap-1.5 text-body-m text-ink-500">
                      <Mail aria-hidden size={14} />
                      <span className="truncate">{u.email}</span>
                    </p>
                    <p className="mt-1 inline-flex items-center gap-1 rounded-full bg-teal-soft px-2 py-0.5 text-body-s font-semibold text-teal">
                      <ShieldCheck aria-hidden size={12} />
                      {ROLE_LABEL[u.role]}
                    </p>
                  </div>
                </section>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <Link to={homeFor(u.role)} className="inline-flex flex-1 items-center justify-center gap-2 rounded-md border border-line-strong bg-surface px-4 py-2 text-body-m font-semibold hover:bg-app">
                    <ArrowLeft aria-hidden size={16} /> Về trang chính
                  </Link>
                  <Button variant="secondary" className="flex-1" onClick={logout} disabled={leaving}>
                    <LogOut aria-hidden size={16} /> Đăng xuất
                  </Button>
                </div>
              </>
            ) : (
              <EmptyBox>
                Bạn chưa đăng nhập.{" "}
                <Link to="/login?next=/me" className="font-semibold text-teal hover:underline">
                  Đăng nhập
                </Link>
              </EmptyBox>
            )
          }
        </AsyncView>
      </main>
    </div>
  );
}
