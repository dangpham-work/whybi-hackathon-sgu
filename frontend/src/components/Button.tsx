import type { ButtonHTMLAttributes } from "react";

/** Nút (Figma mục 04): primary = honey, teal = bắt đầu/tiến trình, secondary = viền, ghost, danger. */
const VARIANTS = {
  primary: "bg-honey text-ink-900 hover:brightness-95",
  teal: "bg-teal text-white hover:brightness-110",
  secondary: "bg-surface text-ink-900 border border-line-strong hover:bg-app",
  ghost: "text-ink-700 hover:bg-app",
  danger: "bg-red-600 text-white hover:bg-red-700",
} as const;

type Props = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof VARIANTS };

export function Button({ variant = "primary", className = "", ...rest }: Props) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-body-m font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${VARIANTS[variant]} ${className}`}
      {...rest}
    />
  );
}
