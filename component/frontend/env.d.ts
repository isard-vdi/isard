/// <reference types="vite/client" />
/// <reference types="vite-svg-loader" />

declare module 'vue-cal' {
  import type { DefineComponent } from 'vue'
  const VueCal: DefineComponent<Record<string, unknown>, object, unknown>
  export default VueCal
}

declare module '@isard/guacamole-common-js' {
  import * as Guacamole from 'guacamole-common-js'
  const GuacamoleCommon: typeof Guacamole & {
    AudioContextFactory: { singleton: AudioContext | null }
  }
  export default GuacamoleCommon
}

declare module 'vue-cal/dist/vuecal.css'
declare module 'vue-cal/dist/i18n/*'

declare const __APP_VERSION__: string

declare module 'punycode/punycode.es6.js' {
  export function toUnicode(input: string): string
}
