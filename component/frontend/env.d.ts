/// <reference types="vite/client" />
/// <reference types="vite-svg-loader" />

declare module 'vue-cal' {
  import type { DefineComponent } from 'vue'
  const VueCal: DefineComponent<Record<string, unknown>, object, unknown>
  export default VueCal
}

declare module 'vue-cal/dist/vuecal.css'
declare module 'vue-cal/dist/i18n/*'
