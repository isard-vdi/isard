// @ts-check
import { test as base, expect } from '@playwright/test'
import { fixture as navbarFixture } from '../navbar'
import { PageAdminTemplates } from './templates-page'
import { PageAdminDownloads } from './downloads-page'
import { ApiHelper } from '../helpers/api'

const test = base.extend({
  ...navbarFixture,

  api: async ({ baseURL }, use) => {
    const api = new ApiHelper(baseURL)
    await api.login()
    await use(api)
  }
})

test.describe.configure({ mode: 'serial' })

test.describe('Template tree deletion', () => {
  /** @type {string} */
  let tetrosTemplateId

  // ---------------------------------------------------------------
  // Ensure TetrOS is downloaded (shared across tests)
  // ---------------------------------------------------------------

  test('setup: download TetrOS', async ({ page, administration }) => {
    const downloads = new PageAdminDownloads(page)
    await downloads.goto()
    await downloads.download('TetrOS')
  })

  // ---------------------------------------------------------------
  // 1. Basic tree: template -> desktop shows role + correct columns
  // ---------------------------------------------------------------

  test('modal shows role column and correct tree for same-category items', async ({ page, api, administration }) => {
    const templates = await api.getTemplates()
    const tetros = templates.find(t => t.name && t.name.includes('TetrOS'))
    expect(tetros).toBeTruthy()
    tetrosTemplateId = tetros.id

    // admin creates desktop -> template -> desktop chain
    const dsk1 = await api.createDesktop('treedsk1-' + Date.now(), tetrosTemplateId)
    await api.waitForDomainStatus(dsk1.id, 'Stopped', 60000)

    const childTmplName = 'treetmpl-' + Date.now()
    const childTmpl = await api.createTemplate(childTmplName, dsk1.id)

    const dsk2Name = 'treedsk2-' + Date.now()
    const dsk2 = await api.createDesktop(dsk2Name, childTmpl.id)
    await api.waitForDomainStatus(dsk2.id, 'Stopped', 60000)

    // Open delete modal in webapp admin
    const adminTemplates = new PageAdminTemplates(page)
    await adminTemplates.goto()
    await adminTemplates.clickDelete(childTmplName)

    const rows = await adminTemplates.getTreeRows()
    expect(rows.length).toBeGreaterThanOrEqual(1)

    // Find the child desktop row
    const childRow = rows.find(r => r.title.includes(dsk2Name))
    expect(childRow).toBeTruthy()

    // Role column should show a real value, not empty or "--"
    expect(childRow.role).toBeTruthy()
    expect(childRow.role).not.toBe('')

    // All items are same category -> nothing masked
    for (const row of rows) {
      expect(row.category).not.toBe('-')
      expect(row.user).not.toBe('-')
    }

    // Delete enabled, no manager warning
    expect(await adminTemplates.isDeleteButtonEnabled()).toBe(true)
    expect(await adminTemplates.isManagerWarningVisible()).toBe(false)

    await adminTemplates.closeDeleteModal()
  })

  // ---------------------------------------------------------------
  // 2. Tree with deployment shows deployment rows
  // ---------------------------------------------------------------

  test('modal shows deployments in tree', async ({ page, api, administration }) => {
    const dsk = await api.createDesktop('deploydsk-' + Date.now(), tetrosTemplateId)
    await api.waitForDomainStatus(dsk.id, 'Stopped', 60000)

    const tmplName = 'deploytmpl-' + Date.now()
    const tmpl = await api.createTemplate(tmplName, dsk.id, {
      roles: ['admin'],
      categories: false,
      groups: false,
      users: false
    })

    const deployName = 'testdeploy-' + Date.now()
    await api.createDeployment(deployName, tmpl.id, {
      roles: false,
      categories: false,
      groups: ['default-default'],
      users: false
    })

    const adminTemplates = new PageAdminTemplates(page)
    await adminTemplates.goto()
    await adminTemplates.clickDelete(tmplName)

    const rows = await adminTemplates.getTreeRows()
    const deployRow = rows.find(r => r.kind === 'Deployment')
    expect(deployRow).toBeTruthy()

    await adminTemplates.closeDeleteModal()
  })

  // ---------------------------------------------------------------
  // 3. Cross-category: admin creates shared template,
  //    user in OTHER category creates desktop from it.
  //    Admin sees full data; manager sees masked rows.
  // ---------------------------------------------------------------

  test('admin sees full tree data across categories', async ({ page, api, baseURL, administration }) => {
    // Create a second category + group + user
    const ts = Date.now()
    const cat2 = await api.createCategory('xcat-' + ts)
    const grp2 = await api.createGroup('xgrp-' + ts, cat2.id)
    const otherUser = 'xuser-' + ts
    await api.createUser(otherUser, cat2.id, grp2.id, 'advanced', 'test1234')

    // Admin creates a shared template (visible to all roles)
    const dsk = await api.createDesktop('xdsk-' + ts, tetrosTemplateId)
    await api.waitForDomainStatus(dsk.id, 'Stopped', 60000)

    const sharedTmplName = 'xshared-' + ts
    const sharedTmpl = await api.createTemplate(sharedTmplName, dsk.id, {
      roles: ['admin', 'manager', 'advanced', 'user'],
      categories: false,
      groups: false,
      users: false
    })

    // Other-category user creates a desktop from the shared template
    const otherApi = new ApiHelper(baseURL)
    const otherToken = await otherApi.loginAs(otherUser, 'test1234', 'xcat-' + ts)
    otherApi.token = otherToken
    const otherDskName = 'xotherdsk-' + ts
    await otherApi.createDesktop(otherDskName, sharedTmpl.id)

    // Admin opens the delete modal -> should see ALL data, no masking
    const adminTemplates = new PageAdminTemplates(page)
    await adminTemplates.goto()
    await adminTemplates.clickDelete(sharedTmplName)

    const rows = await adminTemplates.getTreeRows()
    expect(rows.length).toBeGreaterThanOrEqual(1)

    // Find the cross-category desktop
    const otherRow = rows.find(r => r.title.includes(otherDskName))
    expect(otherRow).toBeTruthy()

    // Admin sees full data: real user, real category, real group
    expect(otherRow.user).not.toBe('-')
    expect(otherRow.category).not.toBe('-')
    expect(otherRow.group).not.toBe('-')
    expect(otherRow.role).not.toBe('-')

    // Delete is enabled for admin (owns everything)
    expect(await adminTemplates.isDeleteButtonEnabled()).toBe(true)
    expect(await adminTemplates.isManagerWarningVisible()).toBe(false)

    await adminTemplates.closeDeleteModal()
  })

  test('manager sees masked rows for other-category derivatives', async ({ page, api, baseURL }) => {
    // Create second category + group + user
    const ts = Date.now()
    const cat2 = await api.createCategory('mcat-' + ts)
    const grp2 = await api.createGroup('mgrp-' + ts, cat2.id)
    const otherUser = 'mother-' + ts
    await api.createUser(otherUser, cat2.id, grp2.id, 'advanced', 'test1234')

    // Create a manager in default category
    const mgrUser = 'mmgr-' + ts
    await api.createUser(mgrUser, 'default', 'default-default', 'manager', 'test1234')

    // Admin creates shared template
    const dsk = await api.createDesktop('mdsk-' + ts, tetrosTemplateId)
    await api.waitForDomainStatus(dsk.id, 'Stopped', 60000)

    const sharedTmplName = 'mshared-' + ts
    const sharedTmpl = await api.createTemplate(sharedTmplName, dsk.id, {
      roles: ['admin', 'manager', 'advanced', 'user'],
      categories: false,
      groups: false,
      users: false
    })

    // Other-category user creates a desktop
    const otherApi = new ApiHelper(baseURL)
    const otherToken = await otherApi.loginAs(otherUser, 'test1234', 'mcat-' + ts)
    otherApi.token = otherToken
    await otherApi.createDesktop('motherdsk-' + ts, sharedTmpl.id)

    // Login as manager in the webapp
    const mgrPage = await page.context().newPage()
    await mgrPage.goto('/login/default')
    await mgrPage.getByPlaceholder('Username').fill(mgrUser)
    await mgrPage.getByPlaceholder('Password').fill('test1234')
    await mgrPage.getByRole('button', { name: 'Login' }).click()
    await mgrPage.waitForURL('/desktops')

    // Navigate to admin templates
    await mgrPage.getByText('Administration').click()
    await mgrPage.waitForURL('/isard-admin/admin/landing')

    const mgrTemplates = new PageAdminTemplates(mgrPage)
    await mgrTemplates.goto()
    await mgrTemplates.clickDelete(sharedTmplName)

    const rows = await mgrTemplates.getTreeRows()
    expect(rows.length).toBeGreaterThanOrEqual(1)

    // The other-category desktop should be MASKED: user/role/category/group all "-"
    const maskedRows = rows.filter(r => r.category === '-')
    expect(maskedRows.length).toBeGreaterThanOrEqual(1)

    for (const masked of maskedRows) {
      expect(masked.user).toBe('-')
      expect(masked.category).toBe('-')
      expect(masked.group).toBe('-')
      expect(masked.title).toBe('-')
    }

    // Manager warning should be visible, delete should be DISABLED
    expect(await mgrTemplates.isManagerWarningVisible()).toBe(true)
    expect(await mgrTemplates.isDeleteButtonEnabled()).toBe(false)

    await mgrPage.close()
  })

  // ---------------------------------------------------------------
  // 4. API-level: manager tree returns pending=true for cross-cat
  // ---------------------------------------------------------------

  test('API returns pending=true for manager with cross-category derivatives', async ({ api, baseURL }) => {
    const ts = Date.now()
    const cat2 = await api.createCategory('acat-' + ts)
    const grp2 = await api.createGroup('agrp-' + ts, cat2.id)
    const otherUser = 'aother-' + ts
    await api.createUser(otherUser, cat2.id, grp2.id, 'advanced', 'test1234')

    const mgrUser = 'amgr-' + ts
    await api.createUser(mgrUser, 'default', 'default-default', 'manager', 'test1234')

    // Admin creates shared template
    const dsk = await api.createDesktop('adsk-' + ts, tetrosTemplateId)
    await api.waitForDomainStatus(dsk.id, 'Stopped', 60000)

    const sharedTmpl = await api.createTemplate('atmpl-' + ts, dsk.id, {
      roles: ['admin', 'manager', 'advanced', 'user'],
      categories: false,
      groups: false,
      users: false
    })

    // Other-category user creates desktop
    const otherApi = new ApiHelper(baseURL)
    otherApi.token = await otherApi.loginAs(otherUser, 'test1234', 'acat-' + ts)
    await otherApi.createDesktop('aotherdsk-' + ts, sharedTmpl.id)

    // Manager fetches tree -> pending must be true
    const mgrApi = new ApiHelper(baseURL)
    mgrApi.token = await mgrApi.loginAs(mgrUser, 'test1234')
    const tree = await mgrApi.getTemplateTree(sharedTmpl.id)

    expect(tree.pending).toBe(true)

    // Admin fetches tree -> pending must be false
    const adminTree = await api.getTemplateTree(sharedTmpl.id)
    expect(adminTree.pending).toBe(false)

    // Admin sees all items with real names
    for (const domain of adminTree.domains) {
      if (Object.keys(domain).length > 0) {
        expect(domain.name).toBeTruthy()
        expect(domain.name).not.toBe('-')
      }
    }
  })

  // ---------------------------------------------------------------
  // 5. Deployment with secondary/linked groups
  // ---------------------------------------------------------------

  test('tree includes deployments targeting linked groups', async ({ api }) => {
    const ts = Date.now()
    const grp1 = await api.createGroup('lgrp1-' + ts, 'default')
    const grp2 = await api.createGroup('lgrp2-' + ts, 'default', [grp1.id])

    const dsk = await api.createDesktop('ldsk-' + ts, tetrosTemplateId)
    await api.waitForDomainStatus(dsk.id, 'Stopped', 60000)

    const tmpl = await api.createTemplate('ltmpl-' + ts, dsk.id, {
      roles: ['admin', 'manager', 'advanced', 'user'],
      categories: false,
      groups: false,
      users: false
    })

    await api.createDeployment('ldeploy-' + ts, tmpl.id, {
      roles: false,
      categories: false,
      groups: [grp2.id],
      users: false
    })

    const tree = await api.getAdminTemplateTree(tmpl.id)
    expect(tree).toBeTruthy()
    expect(tree.length).toBeGreaterThanOrEqual(1)

    // Flatten tree to find deployment
    const allItems = flattenTree(tree)
    const deploy = allItems.find(i => i.kind === 'deployment')
    expect(deploy).toBeTruthy()
  })

  // ---------------------------------------------------------------
  // 6. webapp modal: same-category tree renders role for every row
  // ---------------------------------------------------------------

  test('modal renders role for all same-category rows', async ({ page, api, administration }) => {
    const ts = Date.now()
    const dsk = await api.createDesktop('roledsk-' + ts, tetrosTemplateId)
    await api.waitForDomainStatus(dsk.id, 'Stopped', 60000)

    const tmplName = 'roletmpl-' + ts
    const tmpl = await api.createTemplate(tmplName, dsk.id)

    const dsk2Name = 'roledsk2-' + ts
    await api.createDesktop(dsk2Name, tmpl.id)

    const adminTemplates = new PageAdminTemplates(page)
    await adminTemplates.goto()
    await adminTemplates.clickDelete(tmplName)

    const rows = await adminTemplates.getTreeRows()

    // Every row in the same category should have a role value
    for (const row of rows) {
      expect(row.role).toBeTruthy()
      expect(row.role).not.toBe('')
      expect(row.role).not.toBe('--')
    }

    await adminTemplates.closeDeleteModal()
  })
})

/** Recursively flatten a tree into a flat array */
function flattenTree (nodes) {
  const result = []
  for (const node of nodes) {
    result.push(node)
    if (node.children) {
      result.push(...flattenTree(node.children))
    }
  }
  return result
}
