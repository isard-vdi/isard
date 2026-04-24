import { execFileSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default function globalSetup() {
  if (process.env.E2E_SKIP_SEED === 'true') return
  const script = path.resolve(__dirname, '../db/populate_test_db.py')
  if (!existsSync(script)) return
  try {
    execFileSync('python3', [script], { stdio: 'inherit' })
  } catch (err) {
    // Dev stacks don't always expose the DB host from the Playwright
    // container; tests that need the seeded users will fail on login with a
    // clearer signal than aborting the whole run here.
    console.warn(`[e2e] seed step failed: ${err.message}`)
  }
}
