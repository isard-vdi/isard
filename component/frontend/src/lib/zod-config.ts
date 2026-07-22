// Disable zod v4's JIT fast-path. Zod probes whether `new Function()` is
// available (via `util.allowsEval`) and, if so, compiles object schemas into
// optimized validator functions at runtime. Our CSP (`script-src 'self'`)
// blocks `new Function`, and the probe itself triggers a CSP violation even
// though zod catches the error. Setting `jitless: true` short-circuits the
// probe and makes zod use its interpreter path.
//
// This module must be imported before any module that creates zod schemas at
// import time (top-level `z.object(...)`), so it lives at the top of main.ts.
import { config } from 'zod'

config({ jitless: true })
