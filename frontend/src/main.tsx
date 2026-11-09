import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";
import { onSessionExpired } from "./lib/api";
import { auth } from "./lib/auth";
import { router } from "./router";
import "./styles/index.css";

/**
 * Access token hết hạn (30 phút) mà `api.ts` làm mới cũng không được: dọn phiên và đưa về /login kèm `?next=`
 * để quay lại đúng trang sau khi đăng nhập lại – trước đây không có bước này nên trang "treo" với lỗi 401.
 */
onSessionExpired(() => {
  void auth.logout();
  const next = encodeURIComponent(location.pathname + location.search);
  void router.navigate(`/login?next=${next}`, { replace: true });
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
