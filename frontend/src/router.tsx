import { lazy, Suspense, type ComponentType } from "react";
import { createBrowserRouter, type RouteObject } from "react-router";
import { ScreenPlaceholder } from "./components/ScreenPlaceholder";
import { AdminLayout } from "./layouts/AdminLayout";
import { LecturerLayout } from "./layouts/LecturerLayout";
import { StudentLayout } from "./layouts/StudentLayout";
import { NotFound } from "./pages/NotFound";
import { ScreenIndex } from "./pages/ScreenIndex";
import { SCREENS, type Screen } from "./screens";

/**
 * Route tự nạp (GD-01): màn có file src/pages/<thư mục>/<MÃ bỏ gạch>.tsx (vd. lecturer/GV05.tsx,
 * student/SV04.tsx, auth/AUTH01.tsx) với `export default` sẽ thay trang giữ chỗ – không cần sửa file này.
 * Mỗi route mang `handle: { screen }` để layout dựng breadcrumb / tiêu đề (layouts/shell.tsx).
 */
const pageModules = import.meta.glob<{ default: ComponentType }>("./pages/*/*.tsx");

function element(screen: Screen) {
  const file = Object.keys(pageModules).find((p) => p.endsWith(`/${screen.code.replace("-", "")}.tsx`));
  if (!file) return <ScreenPlaceholder screen={screen} />;
  const Page = lazy(pageModules[file]);
  return (
    <Suspense fallback={<p className="text-ink-500">Đang tải…</p>}>
      <Page />
    </Suspense>
  );
}

const routesFor = (role: Screen["role"]): RouteObject[] =>
  SCREENS.filter((s) => s.role === role).map((s) => ({ path: s.path, element: element(s), handle: { screen: s } }));

/** Cây route – export riêng để test dựng bằng createMemoryRouter. */
export const routes: RouteObject[] = [
  { path: "/", element: <ScreenIndex /> },
  ...routesFor("PUBLIC"),
  { element: <LecturerLayout />, children: routesFor("LECTURER") },
  { element: <StudentLayout />, children: routesFor("STUDENT") },
  { element: <AdminLayout />, children: routesFor("ADMIN") },
  { path: "*", element: <NotFound /> },
];

export const router = createBrowserRouter(routes);
