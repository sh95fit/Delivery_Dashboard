/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_NAVER_MAP_KEY_ID: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
