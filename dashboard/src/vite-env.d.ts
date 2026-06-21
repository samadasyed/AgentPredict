/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Gateway WebSocket URL; when unset the hook falls back to ws://localhost:8000/ws. */
  readonly VITE_GATEWAY_WS_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
