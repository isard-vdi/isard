import { defineConfig } from 'vite'

import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

import svgLoader from 'vite-svg-loader'

// https://vitejs.dev/config/
export default defineConfig({
  base: '/frontend',
  server: {
    allowedHosts: true
  },
  plugins: [
    vue(),
    vueDevTools(),
    tailwindcss(),
    svgLoader({
      defaultImport: 'url'
    })
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  define: {
    // vue-i18n 9 has two message compilers. The default `compileToFunction`
    // path uses `new Function()` (blocked by our CSP: `script-src 'self'`).
    // Setting `__INTLIFY_JIT_COMPILATION__: true` selects the AST-based
    // `compile()` path instead, which is CSP-safe. The flag name is
    // counter-intuitive — "JIT" here means the safe path.
    __INTLIFY_JIT_COMPILATION__: true,
    __INTLIFY_DROP_MESSAGE_COMPILER__: false
  },
  build: {
    // ES2022 needed for top-level await — used by @novnc/novnc 1.6+ in
    // core/util/browser.js for the H.264 WebCodecs capability probe.
    target: 'es2022',
    commonjsOptions: {
      transformMixedEsModules: true
    }
  },
  optimizeDeps: {
    // Dev-mode dep pre-bundling defaults to older browser targets that
    // reject the @novnc/novnc 1.6+ top-level await; mirror build.target.
    esbuildOptions: { target: 'es2022' },
    // @novnc/novnc 1.6 ships CJS files that contain top-level await
    // (lib/util/browser.js:179). esbuild cannot bundle CJS-with-TLA
    // because sibling files use `require()` to load it — illegal in
    // CJS. Skip pre-bundling so Vite's runtime ESM loader handles it.
    exclude: ['@novnc/novnc']
  }
})
