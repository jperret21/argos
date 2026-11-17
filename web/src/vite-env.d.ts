/// <reference types="svelte" />
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ARGOS_API?: string;
  readonly VITE_ARGOS_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
