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
  async login (username = 'admin', password = 'IsardVDI', category = 'default') {
    const token = await this._loginAuth(username, password, category)
    this.token = token
    return { token }
  }

  /**
   * Login as a specific user with their category
   */
  async loginAs (username, password, category = 'default') {
    return this._loginAuth(username, password, category)
  }

  /**
   * Call the Go authentication service at /authentication/login. The
   * endpoint returns the raw JWT in a text/plain body (not JSON) and
   * expects the credentials as multipart/form-data with the provider
   * and category_id as query parameters.
   */
  async _loginAuth (username, password, category) {
    const qs = `provider=form&category_id=${encodeURIComponent(category)}`
    const form = new FormData()
    form.append('username', username)
    form.append('password', password)

    const url = `${this.baseURL}/authentication/login?${qs}`
    const res = await fetchInsecure(url, { method: 'POST', body: form })
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`authentication /login failed (${res.status}): ${text}`)
    }
    return (await res.text()).trim()
  }

  // --- Categories ---

  async createCategory (name, uid) {
    return this._authFetch('POST', '/api/v4/admin/category', {
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
    return this._authFetch('POST', '/api/v4/admin/group', {
      name,
      parent_category: categoryId,
      description: `Test group ${name}`
    })
  }

  // --- Users ---

  async createUser (username, categoryId, groupId, role = 'user', password = 'test1234') {
    return this._authFetch('POST', '/api/v4/admin/user', {
      username,
      uid: username,
      name: username,
      password,
      provider: 'local',
      category: categoryId,
      group: groupId,
      role
    })
  }

  async setSecondaryGroups (userIds, groupIds) {
    return this._authFetch('PUT', '/api/v4/admin/user/secondary-groups/add', {
      ids: userIds,
      secondary_groups: groupIds
    })
  }

  // --- Templates ---

  /**
   * Get the list of available downloads
   */
  async getDownloads (kind = 'domains') {
    return this._authFetch('GET', `/api/v4/admin/downloads/${kind}`)
  }

  /**
   * Register with downloads server if not already registered
   */
  async registerDownloads () {
    return this._authFetch('POST', '/api/v4/admin/downloads/register')
  }

  /**
   * Start downloading a template
   */
  async downloadTemplate (kind, id) {
    return this._authFetch('POST', `/api/v4/admin/downloads/download/${kind}/${id}`)
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
    return this._authFetch('GET', `/api/v4/admin/desktops/tree_list/${templateId}`)
  }

  /**
   * Create a template from a stopped desktop
   */
  async createTemplate (name, desktopId, allowed = false) {
    return this._authFetch('POST', '/api/v4/item/template', {
      name,
      desktop_id: desktopId,
      description: `Test template ${name}`,
      enabled: true,
      allowed: allowed || {
        roles: false,
        categories: false,
        groups: false,
        users: false
      }
    })
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

  async createDeployment (name, templateId, allowed, coOwners = []) {
    return this._authFetch('POST', '/api/v4/item/deployment', {
      name,
      template_id: templateId,
      description: `Test deployment ${name}`,
      desktop_name: `deploy-${name}`,
      visible: true,
      allowed: allowed || {
        roles: false,
        categories: false,
        groups: false,
        users: false
      },
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
    return this._authFetch('DELETE', '/api/v4/admin/user', {
      user: [userId],
      delete_user: true
    })
  }

  // --- Domain status ---

  async getDomain (domainId) {
    return this._authFetch('GET', `/api/v4/item/desktop/${domainId}/get-info`)
  }

  /**
   * Wait for a domain to reach a given status
   */
  async waitForDomainStatus (domainId, status, timeoutMs = 120000) {
    const start = Date.now()
    while (Date.now() - start < timeoutMs) {
      try {
        const domain = await this.getDomain(domainId)
        if (domain.status === status) return domain
      } catch (e) {
        // Domain might not exist yet
      }
      await new Promise(resolve => setTimeout(resolve, 2000))
    }
    throw new Error(`Domain ${domainId} did not reach status ${status} within ${timeoutMs}ms`)
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
    const opts = {
      method,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.token}`
      }
    }
    if (body) opts.body = JSON.stringify(body)

    const res = await fetchInsecure(url, opts)
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`API ${method} ${path} failed (${res.status}): ${text}`)
    }
    return res.json()
  }
}
