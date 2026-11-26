// Build-time deployment settings (Vite inlines import.meta.env.VITE_* at build time).
//   VITE_API_BASE          where the API lives. Local dev: '/api' (Vite proxy). Render: the Railway URL.
//   VITE_PROFILES_ENABLED  'false' hides farmer profiles (no login yet, so the public site does not collect personal data).
export const API_BASE = (import.meta.env.VITE_API_BASE ?? '/api').replace(/\/+$/, '')
export const PROFILES_ENABLED = import.meta.env.VITE_PROFILES_ENABLED !== 'false'
