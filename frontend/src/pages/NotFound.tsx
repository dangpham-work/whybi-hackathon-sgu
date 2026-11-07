import { SearchX } from "lucide-react";
import { Link } from "react-router";
import { Logo } from "../components/Logo";

/** Trang 404 – đường dẫn không có trong src/screens.ts. Không đặt trong thư mục vai để router tự nạp bỏ qua. */
export function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-app p-4">
      <div className="w-full max-w-md rounded-lg border border-line-soft bg-surface p-8 text-center shadow-card">
        <div className="flex justify-center">
          <Logo size={48} />
        </div>
        <h1 className="mt-4 flex items-center justify-center gap-2 text-h2 font-bold">
          <SearchX aria-hidden size={22} className="text-ink-500" /> Không tìm thấy trang
        </h1>
        <p className="mt-2 text-body-m text-ink-500">Đường dẫn này không tồn tại hoặc đã đổi. Hỏi “Tại sao” ở chỗ khác nhé!</p>
        <Link to="/" className="mt-6 inline-block font-semibold text-teal hover:underline">
          Về trang chính
        </Link>
      </div>
    </div>
  );
}
