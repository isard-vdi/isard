// @ts-check
//
// Admin XML-sections editor — Redmine #15065 regression suite.
// Covers the four ticket symptoms:
//   (1) Cache attribute edited via the parent Disks section persists across
//       a save/reload cycle and is mirrored in the Disk Cache view.
//   (2) Disk Cache and Disk QoS panels render read-only with the derived
//       view note (`data-section-derived="1"` + textarea readonly).
//   (3) Lock/Unlock toggle responds on every modal open — the alternation
//       bug from the original 2026-04-16 description (deferred during the
//       branch fix; this spec is the live regression check).
//   (4) Uploading a non-<domain> XML root surfaces an explicit Upload Error
//       toast instead of silently wiping every section.
//
// The spec follows the same pattern as ../admin/template-delete.spec.js:
// Page Object Model, ApiHelper for fixture data, serial mode so a single
// throw-away desktop can be reused across the four scenarios.

import { test as base, expect } from '@playwright/test'
import { fixture as navbarFixture } from '../navbar'
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

let tetrOSChecked = null
const hasTetrOSTemplate = async () => {
  if (tetrOSChecked !== null) return tetrOSChecked
  process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'
  const baseURL =
    process.env.E2E_BASE_URL ?? (process.env.DOCKER ? 'https://host.docker.internal' : 'https://localhost')
  try {
    const fd = new FormData()
    fd.append('username', 'admin')
    fd.append('password', 'IsardVDI')
    const tokRes = await fetch(`${baseURL}/authentication/login?provider=form&category_id=default`, {
      method: 'POST', body: fd
    })
    const tok = (await tokRes.text()).trim()
    const list = await fetch(`${baseURL}/api/v4/items/templates/allowed/all`, {
      headers: { Authorization: `Bearer ${tok}` }
    }).then((r) => r.json()).catch(() => [])
    tetrOSChecked = (Array.isArray(list) ? list : []).some(
      (t) => t.name && t.name.toLowerCase().includes('tetros')
    )
  } catch (e) {
    tetrOSChecked = false
  }
  return tetrOSChecked
}

test.beforeAll(async () => {
  const ok = await hasTetrOSTemplate()
  test.skip(
    !ok,
    'XML sections suite needs the TetrOS template seed — bring up with USAGE=test or run admin/downloads.spec.js first'
  )
})

test.describe('XML sections editor (Redmine #15065)', () => {
  /** @type {string} */
  let testDesktopId

  // -----------------------------------------------------------------
  // Setup: create a throw-away desktop from the bundled TetrOS template
  // (matches what other admin tests do — see template-delete.spec.js).
  // -----------------------------------------------------------------
  test('setup: create test desktop from TetrOS', async ({ api }) => {
    const templates = await api.getTemplates()
    const tetros = templates.find(t => t.name && t.name.includes('TetrOS'))
    expect(tetros, 'TetrOS template not present — run template-delete.spec.js setup first').toBeTruthy()

    const dsk = await api.createDesktop('xmltest-' + Date.now(), tetros.id)
    await api.waitForDomainStatus(dsk.id, 'Stopped', 60000)
    testDesktopId = dsk.id
  })

  // -----------------------------------------------------------------
  // (1) Symptom: editing cache inside the Disks textarea was silently
  // reverted by the unchanged Disk Cache snippet on save.
  // After the fix:  derived sections are skipped on merge, so the parent
  // edit wins and is mirrored in the Disk Cache view.
  // -----------------------------------------------------------------
  test('cache edit in Disks persists and mirrors into Disk Cache view', async ({ page, administration }) => {
    await openXmlEditor(page, testDesktopId)

    const disksTextarea = page.locator('#xml-section-disks .xml-section-textarea')
    await expect(disksTextarea).toBeVisible()
    const before = await disksTextarea.inputValue()

    // Insert cache="writeback" into the existing <driver/> element.
    // Tolerates either self-closing (`<driver ... />`) or open tag variants.
    const edited = before.replace(
      /<driver([^>]*?)\/>/,
      '<driver$1 cache="writeback"/>'
    ).replace(
      /<driver([^>]*?)>/,
      (m, attrs) => attrs.includes('cache=')
        ? m
        : `<driver${attrs} cache="writeback">`
    )
    expect(edited, 'failed to inject cache attribute into the disks snippet').toContain('cache="writeback"')
    await disksTextarea.fill(edited)

    await page.locator('#xmlSectionsSave').click()
    await expect(
      page.locator('.ui-pnotify-text').filter({ hasText: /updated successfully|Updated/i })
    ).toBeVisible({ timeout: 10000 })

    // Reopen and verify both Disks AND Disk Cache views reflect the change.
    await openXmlEditor(page, testDesktopId)
    await expect(page.locator('#xml-section-disks .xml-section-textarea')).toContainText('cache="writeback"')
    await expect(page.locator('#xml-section-disk_cache .xml-section-textarea')).toContainText('cache="writeback"')
  })

  // -----------------------------------------------------------------
  // (2) Disk Cache and Disk QoS are derived informational views.
  // -----------------------------------------------------------------
  test('Disk Cache and Disk QoS render read-only with derived note', async ({ page, administration }) => {
    await openXmlEditor(page, testDesktopId)

    for (const key of ['disk_cache', 'qos_disk']) {
      const panel = page.locator(`#xml-section-${key}`)
      await expect(panel, `${key} panel`).toBeVisible()
      await expect(panel, `${key} panel data-section-derived attribute`).toHaveAttribute('data-section-derived', '1')
      await expect(panel.locator('.xml-section-textarea'), `${key} textarea readonly`).toHaveAttribute('readonly', /.*/)
      await expect(panel, `${key} derived note`).toContainText(/View only/)
    }
  })

  // -----------------------------------------------------------------
  // (3) Lock/Unlock toggle alternation regression.
  // The original bug: clicking the toggle worked on the FIRST modal open
  // but no-op'd on the SECOND. After hoisting the delegated handler to
  // document scope, every open should respond.
  // -----------------------------------------------------------------
  test('Lock toggle responds on first AND second modal open', async ({ page, administration }) => {
    // Open #1 — toggle once.
    await openXmlEditor(page, testDesktopId)
    const toggle1 = page.locator('#xml-section-disks .xml-lock-toggle')
    await expect(toggle1).toBeVisible()
    const initialText = (await toggle1.locator('small').textContent()) || ''
    await toggle1.click()
    await expect(toggle1.locator('small')).not.toHaveText(initialText, { timeout: 2000 })

    // Save (closes the modal) — also persists the protect-state change.
    await page.locator('#xmlSectionsSave').click()
    await expect(page.locator('#modalEditXmlSections')).toBeHidden({ timeout: 10000 })

    // Open #2 — toggle again. This is the open that used to silently fail.
    await openXmlEditor(page, testDesktopId)
    const toggle2 = page.locator('#xml-section-disks .xml-lock-toggle')
    await expect(toggle2).toBeVisible()
    const before2 = (await toggle2.locator('small').textContent()) || ''
    await toggle2.click()
    await expect(
      toggle2.locator('small'),
      'lock toggle did not respond on second modal open (alternation regression)'
    ).not.toHaveText(before2, { timeout: 2000 })
  })

  // -----------------------------------------------------------------
  // (4) Upload of a non-<domain> XML root must surface a clear error and
  // must NOT wipe the textareas.
  // -----------------------------------------------------------------
  test('Upload of non-<domain> XML reports error, does not wipe sections', async ({ page, administration }) => {
    await openXmlEditor(page, testDesktopId)

    const disksTextarea = page.locator('#xml-section-disks .xml-section-textarea')
    const before = await disksTextarea.inputValue()
    expect(before.trim().length).toBeGreaterThan(0)

    const fragment =
      '<disk type="file" device="disk">' +
      '<driver name="qemu" type="qcow2"/>' +
      '<source file="/tmp/x.qcow2"/>' +
      '<target dev="vda" bus="virtio"/>' +
      '</disk>'
    await page.locator('#xmlUploadFile').setInputFiles({
      name: 'fragment.xml',
      mimeType: 'application/xml',
      buffer: Buffer.from(fragment)
    })

    await expect(
      page.locator('.ui-pnotify-title').filter({ hasText: 'Upload Error' })
    ).toBeVisible({ timeout: 10000 })

    // Disks textarea must be untouched.
    await expect(disksTextarea).toHaveValue(before)
  })
})

/**
 * Helper: navigate to admin/Desktops, filter by domain id, click the
 * .btn-xml row action and wait for the modal to be ready.
 *
 * @param {import('@playwright/test').Page} page
 * @param {string} domainId
 */
async function openXmlEditor (page, domainId) {
  await page.goto('/isard-admin/admin/domains/render/Desktops')
  await expect(page.locator('table#domains')).toBeVisible({ timeout: 15000 })

  const search = page.locator('#domains_filter input[type="search"]')
  await search.fill(domainId)
  await page.waitForTimeout(500) // DataTable filter debounce

  const row = page.locator(`table#domains tbody tr[data-pk="${domainId}"]`)
  await expect(row).toBeVisible({ timeout: 5000 })
  await row.locator('.btn-xml').click()

  const modal = page.locator('#modalEditXmlSections')
  await expect(modal).toBeVisible({ timeout: 10000 })
  // Wait for at least one panel to render so subsequent locators don't race.
  await expect(page.locator('#xml-section-disks')).toBeVisible({ timeout: 10000 })
}
