// @ts-check

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
    const res = await this._fetch('POST', '/api/v3/login', {
      type: 'local',
      category_id: category,
      username,
      password
    })
    this.token = res.token
    return res
  }

  /**
   * Login as a specific user with their category
   */
  async loginAs (username, password, category = 'default') {
    const res = await this._fetch('POST', '/api/v3/login', {
      type: 'local',
      category_id: category,
      username,
      password
    })
    return res.token
  }

  // --- Categories ---

  async createCategory (name, uid) {
    return this._authFetch('POST', '/api/v3/admin/category', {
      name,
      uid: uid || name.toLowerCase().replace(/[^a-z0-9]/g, '_'),
      description: `Test category ${name}`
    })
  }

  // --- Groups ---

  async createGroup (name, categoryId, linkedGroups = []) {
    return this._authFetch('POST', '/api/v3/admin/group', {
      name,
      uid: name.toLowerCase().replace(/[^a-z0-9]/g, '_'),
      parent_category: categoryId,
      description: `Test group ${name}`,
      linked_groups: linkedGroups
    })
  }

  // --- Users ---

  async createUser (username, categoryId, groupId, role = 'user', password = 'test1234') {
    return this._authFetch('POST', '/api/v3/admin/user', {
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
    return this._authFetch('PUT', '/api/v3/admin/user/secondary-groups/add', {
      ids: userIds,
      secondary_groups: groupIds
    })
  }

  // --- Templates ---

  /**
   * Get the list of available downloads
   */
  async getDownloads (kind = 'domains') {
    return this._authFetch('GET', `/api/v3/admin/downloads/${kind}`)
  }

  /**
   * Register with downloads server if not already registered
   */
  async registerDownloads () {
    return this._authFetch('POST', '/api/v3/admin/downloads/register')
  }

  /**
   * Start downloading a template
   */
  async downloadTemplate (kind, id) {
    return this._authFetch('POST', `/api/v3/admin/downloads/download/${kind}/${id}`)
  }

  /**
   * Get all templates accessible to the logged-in user
   */
  async getTemplates () {
    return this._authFetch('GET', '/api/v3/user/templates/allowed/all')
  }

  /**
   * Get template tree for deletion
   */
  async getTemplateTree (templateId) {
    return this._authFetch('GET', `/api/v3/template/tree/${templateId}`)
  }

  /**
   * Get admin template tree list
   */
  async getAdminTemplateTree (templateId) {
    return this._authFetch('GET', `/api/v3/admin/desktops/tree_list/${templateId}`)
  }

  /**
   * Create a template from a stopped desktop
   */
  async createTemplate (name, desktopId, allowed = false) {
    return this._authFetch('POST', '/api/v3/template', {
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
    return this._authFetch('POST', `/api/v3/template/duplicate/${templateId}`, {
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
    return this._authFetch('POST', '/api/v3/persistent_desktop', {
      name,
      template_id: templateId,
      description: `Test desktop ${name}`
    })
  }

  async stopDesktop (desktopId) {
    return this._authFetch('PUT', `/api/v3/desktop/updating/${desktopId}`, {
      status: 'Stopping'
    })
  }

  async getDesktop (desktopId) {
    return this._authFetch('GET', `/api/v3/domain/info/${desktopId}`)
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

  async createDeployment (name, templateId, allowed) {
    return this._authFetch('POST', '/api/v3/deployments', {
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
      }
    })
  }

  // --- Domain status ---

  async getDomain (domainId) {
    return this._authFetch('GET', `/api/v3/domain/info/${domainId}`)
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

    const res = await fetch(url, opts)
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

    const res = await fetch(url, opts)
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`API ${method} ${path} failed (${res.status}): ${text}`)
    }
    return res.json()
  }
}
