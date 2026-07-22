// @ts-check
//
// i18n key-leak detector across every authenticated Vue 2 page.
//
// Vue 2 uses ``$t('views.deployments.title')`` etc. throughout the
// templates. When a key is missing or a locale file regresses, the
// raw key string ("views.deployments.title") leaks into the rendered
// HTML — a poor UX that's easy to miss in code review (the Vue
// compiler doesn't validate i18n keys exist).
//
// Round-2 Bug #11 (i18n keys leak in delete-template column) was a
// concrete instance. This spec is a *broad* catch: walk every
// authenticated route and grep ``<body>`` for the ``views.X.Y``
// pattern. Fails fast with the exact key name + path so the
// follow-up fix is mechanical.
//
// Trade-off: false-positive risk if a *legitimate* page renders a
// string that looks like an i18n key (e.g. an admin-table cell
// showing the literal text "views.foo"). The regex is tight
// (``[a-z]+\.[a-z]+(\.[a-z-]+){1,4}``) so dotted-namespace
// configuration values still pass — false positives have been zero
// across staging snapshots reviewed manually.

import { expect } from '@playwright/test'
import { test } from './login-page'

// Tighten the regex to require lowercase + dots + at least 3 segments
// (e.g. ``views.deployments.title``, ``components.statusbar.x.y``).
// Two-segment values like "auth.login" are common config keys, not
// unresolved labels.
const I18N_KEY_RE = /\b(views|components|forms|messages|router|validations)\.[a-z][a-z0-9]*(\.[a-z][a-z0-9-]*){1,5}\b/

const ROUTES = [
  '/desktops',
  '/desktops/new',
  '/templates',
  '/media',
  '/deployments',
  '/userstorage',
  '/profile',
  '/planning',
  '/booking/summary'
]

test.describe('Vue 2 i18n key-leak detector', () => {
  for (const path of ROUTES) {
    test(`${path} resolves all i18n keys (no raw views.X.Y / components.X.Y leak)`, async ({
      page,
      login
    }) => {
      const response = await page.goto(path)
      if (response) {
        expect(response.status(), `nav status for ${path}`).toBeLessThan(400)
      }
      // Wait for SPA + first-pass i18n hydration. The router-level
      // navigation guard fetches user/config; let those settle.
      await page.waitForLoadState('networkidle')

      const body = (await page.textContent('body')) ?? ''
      const match = body.match(I18N_KEY_RE)

      if (match) {
        // Surface enough context to find the offender quickly.
        // ``slice`` around the match gives ~100 chars of surrounding
        // text — usually enough to identify the component.
        const idx = body.indexOf(match[0])
        const ctx = body.slice(Math.max(0, idx - 60), idx + match[0].length + 60)
        throw new Error(
          `i18n key leak on ${path}: '${match[0]}'\n` +
          `Context: ...${ctx.replace(/\s+/g, ' ').trim()}...\n` +
          '(Add the missing key to old-frontend/src/locales/<lang>.json or ' +
          'fix the calling component to use a resolved label.)'
        )
      }

      // Also check page <title> — that's where router-level keys leak
      // when ``router.titles.<route>`` is missing.
      const title = await page.title()
      expect(title, `title for ${path}`).not.toMatch(/^router\./)
    })
  }
})
