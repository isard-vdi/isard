import { defineConfig } from 'vite'
import { readFileSync } from 'node:fs'

import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

import svgLoader from 'vite-svg-loader'

// @novnc/novnc 1.6 ships a CJS file (lib/util/browser.js) that contains a
// top-level await for H.264 WebCodecs capability detection. Four sibling
// files require() that file synchronously — illegal for CJS-with-TLA —
// so esbuild refuses to pre-bundle the package. Excluding it from
// pre-bundling makes the browser fail too: vite serves the raw CJS as
// ESM and the `import RFB from '@novnc/novnc'` default import explodes
// with `doesn't provide an export named: 'default'`.
//
// This esbuild plugin rewrites the offending await into a fire-and-forget
// Promise during pre-bundling. The H.264 capability probe still runs;
// callers read `false` until it resolves, then the updated value. RFB
// gracefully falls back to non-H.264 decoders during the brief window.
const novncTlaShimPlugin = {
  name: 'novnc-tla-shim',
  setup(build: { onLoad: (filter: object, callback: (args: { path: string }) => Promise<{ contents: string; loader: string }>) => void }) {
    build.onLoad(
      { filter: /node_modules\/@novnc\/novnc\/lib\/util\/browser\.js$/ },
      async (args) => {
        const original = readFileSync(args.path, 'utf8')
        const patched = original.replace(
          /exports\.supportsWebCodecsH264Decode = supportsWebCodecsH264Decode = await _checkWebCodecsH264DecodeSupport\(\);/,
          'exports.supportsWebCodecsH264Decode = supportsWebCodecsH264Decode = false;\n_checkWebCodecsH264DecodeSupport().then(function(v) { exports.supportsWebCodecsH264Decode = supportsWebCodecsH264Decode = v; });'
        )
        return { contents: patched, loader: 'js' }
      }
    )
  }
}

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
    esbuildOptions: {
      target: 'es2022',
      plugins: [novncTlaShimPlugin]
    }
  }
})
