// @ts-check
import { test as base } from './base'
import { fixture as fixtureUsers } from './admin/users-page'
import { PageRegister } from './register-page'
import { PageLogin } from './login-page'

const test = base.extend({ ...fixtureUsers })

// Probe ``/authentication/providers`` and the per-provider
// metadata endpoints to discover which providers are FULLY
// configured (not just listed). The dev (USAGE=build) cfg may
// list ``saml`` because the apiv4 middleware loads, but the
// test IdP container (kristophjunge/test-saml-idp) is absent
// so the actual flow 5xxs. USAGE=test brings the IdP up.
let availableProviders = null
const fetchProviders = async () => {
  if (availableProviders) return availableProviders
  process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'
  const baseURL =
    process.env.E2E_BASE_URL ?? (process.env.DOCKER ? 'https://host.docker.internal' : 'https://localhost')
  /** @type {string[]} */
  let listed = []
  try {
    const res = await fetch(`${baseURL}/authentication/providers?category_id=default`)
    const data = await res.json()
    listed = Array.isArray(data?.providers) ? data.providers : []
  } catch (e) { /* skip everything */ }

  const usable = []
  for (const p of listed) {
    if (p === 'form' || p === 'local') {
      usable.push(p)
      continue
    }
    if (p === 'saml') {
      try {
        const r = await fetch(`${baseURL}/authentication/saml/metadata`)
        if (r.ok) usable.push('saml')
      } catch (e) { /* skip */ }
      continue
    }
    if (p === 'ldap') {
      // The Go service won't expose ldap unless it can reach
      // the LDAP server, so listing is sufficient.
      usable.push('ldap')
      continue
    }
    usable.push(p)
  }
  availableProviders = usable
  return availableProviders
}

test.describe('Login', () => {
  test('should login locally correctly against the DB', async ({ page }) => {
    const login = new PageLogin(page)
    await login.goto()
    await login.form(process.env.E2E_ADMIN_USERNAME ?? 'admin', process.env.E2E_ADMIN_PASSWORD ?? 'IsardVDI')
    await login.finished()
  })

  test('should login correctly using LDAP (autoregistration)', async ({ page }) => {
    const providers = await fetchProviders()
    test.skip(
      !providers.includes('ldap'),
      'LDAP provider absent from /authentication/providers — bring up with USAGE=test (isard-authentication-test-ldap container) or configure an external LDAP'
    )
    const login = new PageLogin(page)
    await login.goto()
    await login.form('fry', 'fry')
    await login.finished()
  })

  test('should login correctly using SAML (code registration)', async ({ page, adminUsers }) => {
    const providers = await fetchProviders()
    test.skip(
      !providers.includes('saml'),
      'SAML provider absent from /authentication/providers — bring up with USAGE=test (isard-authentication-test-saml container) or configure an external SAML IdP'
    )
    const login = new PageLogin(page)
    const register = new PageRegister(page)

    await login.goto()
    await login.saml('user1', 'user1pass')

    await register.goto()
    await register.register(adminUsers.registerCode)
    await register.finished()
  })
})
