import { ExternalLink } from "lucide-react";
import { figmaUrl, type Screen } from "../screens";

/**
 * Trang giữ chỗ cho màn chưa dựng. Thay bằng màn thật trong thẻ GD tương ứng:
 * tạo file src/pages/<role>/<CODE>.tsx (vd. pages/lecturer/GV05.tsx) export default component – router tự nạp.
 */
export function ScreenPlaceholder({ screen }: { screen: Screen }) {
  return (
    <div className="mx-auto max-w-3xl rounded-lg border border-dashed border-line-strong bg-surface p-8 shadow-card">
      <p className="caps">
        {screen.code} · Vòng {screen.round} · Thẻ {screen.card}
      </p>
      <h1 className="mt-2 text-h1 font-bold">{screen.title}</h1>
      <p className="mt-2 text-body-m text-ink-500">Yêu cầu: {screen.reqs}</p>
      <div className="mt-6 flex flex-wrap gap-3 text-body-m">
        {screen.figmaNode && (
          <a className="inline-flex items-center gap-1 font-semibold text-teal hover:underline" href={figmaUrl(screen.figmaNode)} target="_blank" rel="noreferrer">
            Mở thiết kế Figma <ExternalLink size={14} />
          </a>
        )}
        {screen.figmaNode ? (
          <code className="rounded-sm bg-app px-2 py-1 text-ink-700">docs/design/screens/{screen.code}.png</code>
        ) : (
          <span className="text-ink-500">Chưa có Figma – dựng theo khung chung</span>
        )}
      </div>
    </div>
  );
}
