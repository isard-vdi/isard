// @ts-check

// Stack ships a self-signed certificate; the playwright config's
// ``ignoreHTTPSErrors: true`` only applies to the page context, not
// to global ``fetch``. Disable TLS verification at the Node level
// before any fetch happens.
process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'

const fetchInsecure = (url, init = {}) => fetch(url, init)

/**
 * API helper for creating test data via IsardVDI REST API.
 * Used by Playwright tests to set up categories, groups, users,
 * templates, desktops, and deployments.
 */
export class ApiHelper {
  /**
   * @param {string} baseURL
   */
  constructor (baseURL) {
    this.baseURL = baseURL
    this.token = null
  }

  /**
   * Login as admin and store the token
   */
  // Defaults honour the E2E_ADMIN_* env overrides so spec-local
  // ``seed.login()`` calls work on stacks with a non-default admin
  // password (they previously 401'd deterministically there).
  async login (username = process.env.E2E_ADMIN_USERNAME ?? 'admin', password = process.env.E2E_ADMIN_PASSWORD ?? 'IsardVDI', category = 'default') {
    const token = await this._loginAuth(username, password, category)
    this.token = token
    // Stash credentials so ``_authFetch`` can re-login on 401
    // ``Session expired`` (cross-worker session shadowing).
    this._lastUsername = username
    this._lastPassword = password
    this._lastCategory = category
    return { token }
  }

  /**
   * Login as a specific user with their category
   */
  async loginAs (username, password, category = 'default') {
    const token = await this._loginAuth(username, password, category)
    this.token = token
    this._lastUsername = username
    this._lastPassword = password
    this._lastCategory = category
    return token
  }

  /**
   * Call the Go authentication service at /authentication/login. The
   * endpoint returns the raw JWT in a text/plain body (not JSON) and
   * expects the credentials as multipart/form-data with the provider
   * and category_id as query parameters.
   *
   * Newly-created users get a ``disclaimer-acknowledgement-required``
   * JWT on first login; that token can't reach /api/v4/. Detect the
   * type, POST /authentication/acknowledge-disclaimer with it, then
   * re-login to get a real session JWT.
   */
  async _loginAuth (username, password, category) {
    const qs = `provider=form&category_id=${encodeURIComponent(category)}`
    const url = `${this.baseURL}/authentication/login?${qs}`

    const buildForm = () => {
      const form = new FormData()
      form.append('username', username)
      form.append('password', password)
      return form
    }

    const doLogin = async () => {
      const res = await fetchInsecure(url, { method: 'POST', body: buildForm() })
      if (!res.ok) {
        const text = await res.text()
        if (res.status === 429) {
          // Tests MUST run with the login rate limiter disabled — a serial
          // suite logs in once per test and trips it, cascading the whole
          // run into 429s. Fail with the fix instead of a mystery.
          throw new Error(
            'authentication /login rate-limited (429). Test stacks must set ' +
            'AUTHENTICATION_AUTHENTICATION_LIMITS_ENABLED=false in the cfg ' +
            '(then bash build.sh && docker compose up -d isard-authentication). ' +
            `Server said: ${text}`
          )
        }
        throw new Error(`authentication /login failed (${res.status}): ${text}`)
      }
      return (await res.text()).trim()
    }

    let token = await doLogin()

    // Decode the JWT payload to detect the disclaimer-required state.
    const decodePayload = (jwt) => {
      try {
        const seg = jwt.split('.')[1]
        const padded = seg + '='.repeat((4 - (seg.length % 4)) % 4)
        return JSON.parse(Buffer.from(padded, 'base64').toString('utf-8'))
      } catch (e) {
        return {}
      }
    }
    const payload = decodePayload(token)
    if (payload.type === 'disclaimer-acknowledgement-required') {
      const ackRes = await fetchInsecure(
        `${this.baseURL}/authentication/acknowledge-disclaimer`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: '{}'
        }
      )
      if (!ackRes.ok) {
        const text = await ackRes.text()
        throw new Error(`authentication /acknowledge-disclaimer failed (${ackRes.status}): ${text}`)
      }
      token = await doLogin()
    }
    return token
  }

  // --- Categories ---

  async createCategory (name, uid) {
    return this._authFetch('POST', '/api/v4/admin/item/category', {
      name,
      uid: uid || name.toLowerCase().replace(/[^a-z0-9]/g, '_'),
      description: `Test category ${name}`
    })
  }

  // --- Groups ---

  async createGroup (name, categoryId, linkedGroups = []) {
    // v4 AdminGroupCreateData does not accept `linked_groups`; the caller
    // argument is kept for API compatibility and currently ignored. If
    // tests need linked-groups, a follow-up PUT to the group is needed.
    return this._authFetch('POST', '/api/v4/admin/item/group', {
      name,
      parent_category: categoryId,
      description: `Test group ${name}`
    })
  }

  // --- Users ---

  async createUser (username, categoryId, groupId, role = 'user', password = 'test1234') {
    const user = await this._authFetch('POST', '/api/v4/admin/item/user', {
      username,
      uid: username,
      name: username,
      password,
      provider: 'local',
      category: categoryId,
      group: groupId,
      role
    })
    // Pre-acknowledge the disclaimer for the synthetic user.
    // Without this, every subsequent login by ``username``
    // produces a disclaimer-required JWT that can't reach
    // /api/v4/, so role-based UI tests for newly-created users
    // get 403 on every protected endpoint until they manually
    // walk through /disclaimer.
    try {
      await this._loginAuth(username, password, categoryId)
    } catch (e) {
      // Best-effort — disclaimer ack is the user's first login;
      // _loginAuth already does it inline. If login fails for
      // another reason (e.g. password policy), surface the user
      // anyway and let the calling test fail explicitly.
      console.warn(`createUser: post-create ack-disclaimer login failed: ${e.message}`)
    }
    return user
  }

  async setSecondaryGroups (userIds, groupIds) {
    return this._authFetch('PUT', '/api/v4/admin/item/user/secondary-groups/add', {
      ids: userIds,
      secondary_groups: groupIds
    })
  }

  // --- Templates ---

  /**
   * Get the list of available downloads
   */
  async getDownloads (kind = 'domains') {
    return this._authFetch('GET', `/api/v4/admin/items/downloads/${kind}`)
  }

  /**
   * Register with downloads server if not already registered
   */
  async registerDownloads () {
    return this._authFetch('POST', '/api/v4/admin/item/downloads/register')
  }

  /**
   * Start downloading a template
   */
  async downloadTemplate (kind, id) {
    return this._authFetch('POST', `/api/v4/admin/item/downloads/download/${kind}/${id}`)
  }

  /**
   * Get all templates accessible to the logged-in user
   */
  async getTemplates () {
    return this._authFetch('GET', '/api/v4/items/templates/allowed/all')
  }

  /**
   * Get template tree for deletion
   */
  async getTemplateTree (templateId) {
    return this._authFetch('GET', `/api/v4/item/template/${templateId}/get-tree`)
  }

  /**
   * Get admin template tree list
   */
  async getAdminTemplateTree (templateId) {
    return this._authFetch('GET', `/api/v4/admin/items/desktops/tree_list/${templateId}`)
  }

  /**
   * Create a template from a stopped desktop.
   *
   * The desktop's underlying storage may still have a pending
   * task (qcow2 chain creation) even after the desktop reaches
   * Stopped — apiv4 returns 428 ``storage_pending_task`` if you
   * try to create a template while that pending task is alive.
   * Retry a few times with backoff so callers don't have to
   * thread the storage state machine into every test.
   */
  async createTemplate (name, desktopId, allowed = false) {
    const buildBody = (n) => ({
      name: n,
      desktop_id: desktopId,
      description: `Test template ${n}`,
      enabled: true,
      allowed: allowed || {
        roles: false,
        categories: false,
        groups: false,
        users: false
      }
    })
    const deadline = Date.now() + 30000
    let attempt = 0
    let lastErr = null
    while (Date.now() < deadline) {
      // apiv4 inserts the template row BEFORE enqueueing the
      // storage task, so a 428 on the second step leaves the row
      // behind. Subsequent attempts hit 409 ``name_exists``. Bump
      // the name suffix per retry so the row insert succeeds and
      // we eventually pick up the storage when it's free.
      const attemptName = attempt === 0 ? name : `${name}-r${attempt}`
      try {
        return await this._authFetch('POST', '/api/v4/item/template', buildBody(attemptName))
      } catch (e) {
        lastErr = e
        // Both apiv4 preconditions are timing-related and clear
        // on their own:
        // * ``storage_pending_task`` — qcow2 chain still being
        //   built.
        // * ``status desktop must be Stopped`` — engine flips the
        //   desktop into Updating right after Stopped while
        //   reservables / hardware metadata is materialised.
        // Both clear within seconds; retry until the deadline.
        const retriable =
          /storage_pending_task|precondition_required.*pending task/i.test(e.message) ||
          /must be Stopped/i.test(e.message) ||
          /new_template_name_exists/.test(e.message)
        if (!retriable) throw e
        attempt += 1
        await new Promise((resolve) => setTimeout(resolve, 1500))
      }
    }
    throw lastErr ?? new Error('createTemplate timed out')
  }

  /**
   * Duplicate a template
   */
  async duplicateTemplate (templateId, name, allowed = false) {
    return this._authFetch('POST', `/api/v4/item/template/${templateId}/duplicate`, {
      name,
      description: 'Duplicate of template',
      enabled: true,
      allowed: allowed || {
        roles: false,
        categories: false,
        groups: false,
        users: false
      }
    })
  }

  // --- Desktops ---

  async createDesktop (name, templateId) {
    return this._authFetch('POST', '/api/v4/item/desktop', {
      name,
      template_id: templateId,
      description: `Test desktop ${name}`
    })
  }

  async startDesktop (desktopId) {
    return this._authFetch('GET', `/api/v3/desktop/start/${desktopId}`)
  }

  async stopDesktop (desktopId) {
    return this._authFetch('PUT', `/api/v4/item/desktop/${desktopId}/stop`)
  }

  async getDesktop (desktopId) {
    return this._authFetch('GET', `/api/v4/item/desktop/${desktopId}/get-info`)
  }

  /**
   * Wait for a desktop to reach a specific status
   */
  async waitForDesktopStatus (desktopId, status, timeoutMs = 60000) {
    const start = Date.now()
    while (Date.now() - start < timeoutMs) {
      const desktop = await this.getDesktop(desktopId)
      if (desktop.status === status) return desktop
      await new Promise(resolve => setTimeout(resolve, 2000))
    }
    throw new Error(`Desktop ${desktopId} did not reach status ${status} within ${timeoutMs}ms`)
  }

  // --- Deployments ---

  // CreateDeploymentRequest now requires a ``desktops`` array
  // (one entry per desktop type) and ``allowed`` only has
  // ``users``/``groups`` — the legacy ``roles``/``categories``
  // keys are ignored. Wrap legacy callers transparently:
  //   * If allowed lacks both users and groups, default
  //     allowed.users to the current admin's user id (the
  //     deployment must be reachable by SOMEONE).
  //   * Synthesize a single CreateDesktopRequest from the
  //     legacy ``template_id`` + ``desktop_name`` arguments.
  async createDeployment (name, templateId, allowed, coOwners = []) {
    const adminFallback = ['local-default-admin-admin']
    const safeAllowed = {
      users: allowed?.users || adminFallback,
      groups: allowed?.groups ?? false
    }
    return this._authFetch('POST', '/api/v4/item/deployment', {
      name,
      description: `Test deployment ${name}`,
      visible: true,
      allowed: safeAllowed,
      desktops: [
        {
          template_id: templateId,
          name: `deploy-${name}`,
          description: `Test deployment desktop ${name}`,
          persistent: true,
          // Most templates ship with ``file_rdpgw`` viewers; the
          // create-deployment endpoint refuses RDP viewers unless a
          // wireguard interface is declared. Force-include it for
          // test-seeded deployments.
          hardware: { interfaces: ['wireguard'] }
        }
      ],
      // ``co_owners`` lets additional users see the deployment as
      // owner-equivalent for read/start/stop, but ONLY the original
      // owner can edit the co-owners list itself. The Bug #47
      // regression spec uses this to seed a deployment whose modal
      // is opened by a co-owner (not the owner) and assert the
      // "Update co-owners" footer button stays hidden.
      co_owners: coOwners
    })
  }

  async deleteDeployment (deploymentId) {
    return this._authFetch(
      'DELETE',
      `/api/v4/item/deployment/${deploymentId}?permanent=true`
    )
  }

  async deleteUser (userId) {
    // ``DELETE /admin/user`` body: AdminUserDeleteData = {user: list[str], delete_user: bool}.
    return this._authFetch('DELETE', '/api/v4/admin/items/users', {
      user: [userId],
      delete_user: true
    })
  }

  // --- Domain status ---

  async getDomain (domainId) {
    return this._authFetch('GET', `/api/v4/item/desktop/${domainId}/get-info`)
  }

  /**
   * Wait for a domain to reach a given status.
   *
   * The ``/item/desktop/{id}/get-info`` response intentionally
   * omits ``status`` (it returns the editable shape). Status is
   * exposed via the listing endpoint ``/items/desktops``, which
   * is what the Vue 2 dashboard uses too. Poll every 1 s — engine
   * typically transitions Creating → Stopped in <10 s on a healthy
   * stack.
   */
  async waitForDomainStatus (domainId, status, timeoutMs = 60000) {
    const start = Date.now()
    while (Date.now() - start < timeoutMs) {
      try {
        const resp = await this._authFetch('GET', '/api/v4/items/desktops')
        const list = Array.isArray(resp) ? resp : resp?.desktops ?? []
        const found = list.find((d) => d.id === domainId)
        if (found?.status === status) return found
        if (found?.status === 'Failed') {
          throw new Error(`Domain ${domainId} reached Failed instead of ${status}`)
        }
      } catch (e) {
        if (/reached Failed/.test(e.message)) throw e
        // Listing may transiently 5xx during heavy churn; keep polling.
      }
      await new Promise((resolve) => setTimeout(resolve, 1000))
    }
    throw new Error(`Domain ${domainId} did not reach status ${status} within ${timeoutMs}ms`)
  }

  /**
   * Set a desktop's viewer.guest_ip via the admin table-update endpoint.
   * Mirrors the apiv4 ``POST /admin/hypervisor/vm/wg_addr`` path that the
   * dnsmasq DHCP hook uses in production: rethinkdb ``.update()`` deep-
   * merges, so the rest of ``viewer`` (passwd, base_port, ports …) is
   * preserved. The same changefeed → change-handler → socketio chain
   * fires, so this is the cheapest way to simulate the WS desktop_update
   * event in e2e without standing up a real hypervisor.
   *
   * @param {string} desktopId
   * @param {string|null} ip  pass null to clear (park back at WaitingIP)
   */
  async setDesktopGuestIp (desktopId, ip) {
    return this._authFetch('PUT', '/api/v4/admin/item/table/update/domains', {
      id: desktopId,
      viewer: { guest_ip: ip }
    })
  }

  /**
   * Poll ``/items/desktops`` until the desktop's listing ``ip`` matches
   * ``expected`` (or null). Companion to ``setDesktopGuestIp`` for tests
   * that assert the WS path delivered the new IP into the listing too.
   */
  async waitForDesktopIp (desktopId, expected, timeoutMs = 10000) {
    const start = Date.now()
    while (Date.now() - start < timeoutMs) {
      try {
        const resp = await this._authFetch('GET', '/api/v4/items/desktops')
        const list = Array.isArray(resp) ? resp : resp?.desktops ?? []
        const found = list.find((d) => d.id === desktopId)
        if (found && (found.ip ?? null) === (expected ?? null)) return found
      } catch (e) {
        // transient listing churn — keep polling
      }
      await new Promise((resolve) => setTimeout(resolve, 500))
    }
    throw new Error(`Desktop ${desktopId} did not reach ip=${expected} within ${timeoutMs}ms`)
  }

  // --- Internal helpers ---

  async _fetch (method, path, body = undefined) {
    const url = `${this.baseURL}${path}`
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' }
    }
    if (body) opts.body = JSON.stringify(body)

    const res = await fetchInsecure(url, opts)
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`API ${method} ${path} failed (${res.status}): ${text}`)
    }
    return res.json()
  }

  async _authFetch (method, path, body = undefined) {
    if (!this.token) throw new Error('Not logged in - call login() first')

    const url = `${this.baseURL}${path}`
    const buildOpts = () => {
      const o = {
        method,
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${this.token}`
        }
      }
      if (body) o.body = JSON.stringify(body)
      return o
    }

    let res = await fetchInsecure(url, buildOpts())

    // Cross-worker session shadowing: when two workers log in as
    // the same user back-to-back, the sessions service may
    // invalidate the older session, so a previously-valid JWT
    // returns 401 ``Session expired``. Retry once after a fresh
    // login — the new session covers this worker's remaining
    // calls until the next shadow event.
    if (res.status === 401 && this._lastUsername) {
      try {
        const newToken = await this._loginAuth(
          this._lastUsername,
          this._lastPassword,
          this._lastCategory
        )
        this.token = newToken
        res = await fetchInsecure(url, buildOpts())
      } catch (e) {
        // Fall through to the original error.
      }
    }

    if (!res.ok) {
      const text = await res.text()
      throw new Error(`API ${method} ${path} failed (${res.status}): ${text}`)
    }
    // ``admin/table/update/*`` and friends respond with 204 No Content;
    // ``res.json()`` blows up on an empty body. Guard against it.
    if (res.status === 204) return null
    const text = await res.text()
    return text ? JSON.parse(text) : null
  }
}
