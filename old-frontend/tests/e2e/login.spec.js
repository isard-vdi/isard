// @ts-check
import { test as base } from './base'
import { fixture as fixtureUsers } from './admin/users-page'
import { PageRegister } from './register-page'
import { PageLogin } from './login-page'

const test = base.extend({ ...fixtureUsers })

// Probe ``/authentication/providers`` to discover which providers
// are configured on the running stack. The dev (USAGE=build) cfg
// has only ``form``; USAGE=test brings up
// ``isard-authentication-test-ldap`` and ``isard-authentication-test-saml``
// so the LDAP/SAML specs can actually run.
let availableProviders = null
const fetchProviders = async () => {
  if (availableProviders) return availableProviders
  process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'
  const baseURL =
    process.env.E2E_BASE_URL ?? (process.env.DOCKER ? 'https://host.docker.internal' : 'https://localhost')
  try {
    const res = await fetch(`${baseURL}/authentication/providers?category_id=default`)
    const data = await res.json()
    availableProviders = Array.isArray(data?.providers) ? data.providers : []
  } catch (e) {
    availableProviders = []
  }
  return availableProviders
}

test.describe('Login', () => {
  test('should login locally correctly against the DB', async ({ page }) => {
    const login = new PageLogin(page)
    await login.goto()
    await login.form('admin', 'IsardVDI')
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
