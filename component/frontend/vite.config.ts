import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

import svgLoader from 'vite-svg-loader'

// @novnc/novnc 1.6 ships a CJS file (lib/util/browser.js) that contains a
// top-level await for H.264 WebCodecs capability detection. Four sibling
// files require() that file synchronously — illegal for CJS-with-TLA —
// so Rolldown refuses to bundle the package. Excluding it from
// pre-bundling makes the browser fail too: vite serves the raw CJS as
// ESM and the `import RFB from '@novnc/novnc'` default import explodes
// with `doesn't provide an export named: 'default'`.
//
// This plugin rewrites the offending await into a fire-and-forget
// Promise, both in the build and in dev pre-bundling. The H.264
// capability probe still runs; callers read `false` until it resolves,
// then the updated value. RFB gracefully falls back to non-H.264
// decoders during the brief window.
const novncTlaShimPlugin: Plugin = {
  name: 'novnc-tla-shim',
  transform: {
    filter: { id: /node_modules\/@novnc\/novnc\/lib\/util\/browser\.js$/ },
    handler(code) {
      // Same-line rewrite, so the original sourcemap still holds.
      const patched = code.replace(
        /exports\.supportsWebCodecsH264Decode = supportsWebCodecsH264Decode = await _checkWebCodecsH264DecodeSupport\(\);/,
        'exports.supportsWebCodecsH264Decode = supportsWebCodecsH264Decode = false; _checkWebCodecsH264DecodeSupport().then(function(v) { exports.supportsWebCodecsH264Decode = supportsWebCodecsH264Decode = v; });'
      )
      return { code: patched, map: null }
    }
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  base: '/frontend',
  server: {
    allowedHosts: true
  },
  plugins: [
    novncTlaShimPlugin,
    vue(),
    // The devtools client instruments every component; a dev tab left open for
    // hours grows past 2 GB. Set VUE_DEVTOOLS=false to leave it out.
    ...(process.env.VUE_DEVTOOLS === 'false' ? [] : [vueDevTools()]),
    tailwindcss(),
    svgLoader({
      defaultImport: 'url'
    })
  ],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src')
    }
  },
  define: {
    // vue-i18n 9 has two message compilers. The default `compileToFunction`
    // path uses `new Function()` (blocked by our CSP: `script-src 'self'`).
    // Setting `__INTLIFY_JIT_COMPILATION__: true` selects the AST-based
    // `compile()` path instead, which is CSP-safe. The flag name is
    // counter-intuitive — "JIT" here means the safe path.
    __INTLIFY_JIT_COMPILATION__: true,
    __INTLIFY_DROP_MESSAGE_COMPILER__: false,
    // Build-time injection of the IsardVDI release id so Faro tags every
    // event with the exact frontend bundle that produced it.
    __APP_VERSION__: JSON.stringify(process.env.SRC_VERSION_ID ?? 'dev')
  },
  build: {
    // ES2022 needed for top-level await — used by @novnc/novnc 1.6+ in
    // core/util/browser.js for the H.264 WebCodecs capability probe.
    target: 'es2022',
    // Public source maps so Faro / Grafana resolve minified stack traces.
    // Frontend is open source — no IP exposure concern.
    sourcemap: true
  },
  legacy: {
    // With "type": "module", Vite 8 dev hands `import RFB from '@novnc/novnc'`
    // the CJS module.exports instead of the RFB class; the build does not.
    inconsistentCjsInterop: true
  },
  optimizeDeps: {
    rolldownOptions: {
      plugins: [novncTlaShimPlugin]
    }
  }
})
