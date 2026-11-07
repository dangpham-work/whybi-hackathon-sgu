/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Token tạm khi chưa có C2-07 (dev-lecturer | dev-student | dev-admin) – chỉ dùng ở `npm run dev`. */
  readonly VITE_DEV_TOKEN?: string;
}
