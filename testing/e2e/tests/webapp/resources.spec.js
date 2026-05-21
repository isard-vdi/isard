// Drives Domains → Resources admin flows on /isard-admin/admin/domains/render/Resources.
// Mirrors testing/e2e/specs/webapp/resources.md.
//
// Conventions:
//   - Setup/cleanup API calls use the generated apiv4 SDK only.
//   - UI verification still listens to network calls fired by the page.
//   - Resource names are tracked in testInfo.annotations so afterEach can clean
//     up even when assertions fail mid-flow.
//   - Uses worker-scoped authenticated context (no login per test).

import { test, expect, unwrap } from '../../fixtures/apiv4/index.js'
import {
  adminAllowedUpdate,
  adminQosDiskAdd,
  adminTableDelete,
  adminTableInsert,
  adminTableList,
  getAdminBastionConfig,
} from '../../src/gen/apiv4/sdk.gen'

const RESOURCES_URL = '/isard-admin/admin/domains/render/Resources'
const VALID_NAME_RE = /^[\-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9:/]+$/

function uniqueName(testInfo, kind, suffix = '') {
  return `e2e-${kind}-${testInfo.workerIndex}-${Date.now()}${suffix ? `-${suffix}` : ''}`
}

function trackName(testInfo, table, name) {
  testInfo.annotations.push({ type: `resource-${table}`, description: name })
}

async function listTable(client, table, body = { order_by: 'name' }) {
  const data = await unwrap(
    adminTableList({ client, path: { table }, body }),
  ).catch(() => [])
  return Array.isArray(data) ? data : data ? [data] : []
}

async function findByName(client, table, name) {
  const rows = await listTable(client, table)
  return rows.find((r) => r?.name === name) || null
}

async function deleteById(client, table, id) {
  await adminTableDelete({ client, path: { table, item_id: id } }).catch(() => {})
}

async function deleteByName(client, table, name) {
  const row = await findByName(client, table, name)
  if (row?.id) await deleteById(client, table, row.id)
}

async function gotoResources(page) {
  await page.goto(RESOURCES_URL)
  // Wait for the main interfaces table wrapper to be visible
  await page
    .locator('#table-interfaces ~ .dataTables_wrapper, .dataTables_wrapper:has(#table-interfaces)')
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
  // Wait for at least one data row (not .dataTables_empty) to ensure data loaded
  await page
    .locator('#table-interfaces tbody tr:not(.dataTables_empty)')
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
}

async function clickPnotifyButton(page, text) {
  await page
    .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: new RegExp(`^${text}$`, 'i') })
    .first()
    .click({ timeout: 5000 })
}

async function toggleAllowedsRolesAndSave(page, table) {
  const modal = page.locator('#modalAlloweds')
  await modal.waitFor({ state: 'visible', timeout: 10000 })

  const rolesChecked = () => page.evaluate(() => document.querySelector('#a-roles-cb')?.checked ?? null)
  const initial = await rolesChecked()

  await modal.locator('#roles_pannel .iCheck-helper').first().click({ force: true })
  await expect.poll(rolesChecked, { timeout: 5000 }).not.toBe(initial)

  const save = page.waitForResponse(
    (r) =>
      r.url().includes(`/api/v4/item/allowed/update/${table}`) &&
      r.request().method() === 'POST',
    { timeout: 15000 },
  )
  await modal.locator('#send').click()
  expect((await save).status()).toBeLessThan(400)
  await modal.waitFor({ state: 'hidden', timeout: 8000 })
}

test.describe('Admin Resources — webapp', () => {
  test.describe.configure({ mode: 'serial' })

  test.afterEach(async ({ apiv4Admin }, testInfo) => {
    const mapping = {
      qos_net: 'qos_net',
      qos_disk: 'qos_disk',
      interfaces: 'interfaces',
      videos: 'videos',
      remotevpn: 'remotevpn',
    }

    for (const annotation of testInfo.annotations) {
      const prefix = 'resource-'
      if (!annotation.type.startsWith(prefix)) continue
      const key = annotation.type.slice(prefix.length)
      const table = mapping[key]
      if (!table) continue
      await deleteByName(apiv4Admin, table, annotation.description)
    }
  })

  test('A1: creates a Network QoS from modal', async ({ authenticatedPage: page, apiv4Admin }, testInfo) => {
    const name = uniqueName(testInfo, 'qosnet')
    expect(name).toMatch(VALID_NAME_RE)
    trackName(testInfo, 'qos_net', name)

    await gotoResources(page)
    await page.locator('.add-new-qos-net').click()

    const modal = page.locator('#modalQosNet')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await modal.locator('#name').fill(name)
    await modal.locator('#description').fill('e2e qos net create')
    await modal.locator('#qos-bandwidth-inbound-average').fill('10000')
    await modal.locator('#qos-bandwidth-inbound-peak').fill('15000')
    await modal.locator('#qos-bandwidth-inbound-floor').fill('5000')
    await modal.locator('#qos-bandwidth-inbound-burst').fill('20000')
    await modal.locator('#qos-bandwidth-outbound-average').fill('10000')
    await modal.locator('#qos-bandwidth-outbound-peak').fill('15000')
    await modal.locator('#qos-bandwidth-outbound-burst').fill('20000')

    const createResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/item/table/add/qos_net') && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await createResp).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    await expect(page.locator(`#table-qos-net tbody tr:has-text("${name}")`).first())
      .toBeVisible({ timeout: 10000 })

    const saved = await findByName(apiv4Admin, 'qos_net', name)
    expect(saved).not.toBeNull()
  })

  test('A2: edits a Network QoS from table row', async ({ authenticatedPage: page, apiv4Admin }, testInfo) => {
    const name = uniqueName(testInfo, 'qosnet-edit')
    trackName(testInfo, 'qos_net', name)

    await unwrap(
      adminTableInsert({
        client: apiv4Admin,
        path: { table: 'qos_net' },
        body: {
          name,
          description: 'before edit',
          allowed: { roles: false, categories: false, groups: false, users: false },
          bandwidth: {
            inbound: { '@average': 10000, '@peak': 15000, '@floor': 5000, '@burst': 20000 },
            outbound: { '@average': 10000, '@peak': 15000, '@burst': 20000 },
          },
        },
      }),
    )

    await gotoResources(page)
    const row = page.locator(`#table-qos-net tbody tr:has-text("${name}")`).first()
    await expect(row).toBeVisible({ timeout: 10000 })
    await row.locator('button#btn-edit').click()

    const modal = page.locator('#modalQosNet')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await modal.locator('#description').fill('after edit')
    await modal.locator('#qos-bandwidth-inbound-average').fill('8000')

    const editResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/item/table/update/qos_net') && r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await editResp).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    await expect(row).toContainText('after edit', { timeout: 10000 })
  })

  test('B1: creates a Disk QoS from modal', async ({ authenticatedPage: page, apiv4Admin }, testInfo) => {
    const name = uniqueName(testInfo, 'qosdisk')
    trackName(testInfo, 'qos_disk', name)

    await gotoResources(page)
    await page.locator('.add-new-qos-disk').click()
    const modal = page.locator('#modalQosDisk')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    await modal.locator('#name').fill(name)
    await modal.locator('#description').fill('disk qos create')
    await modal.locator('#iotune_megabytes-read_bytes_sec').fill('50')
    await modal.locator('#iotune_megabytes-write_bytes_sec').fill('50')
    await modal.locator('#iotune_megabytes-read_bytes_sec_max').fill('80')
    await modal.locator('#iotune_megabytes-write_bytes_sec_max').fill('80')
    await modal.locator('#iotune-read_bytes_sec_max_length').fill('2')
    await modal.locator('#iotune-write_bytes_sec_max_length').fill('2')
    await modal.locator('#iotune-read_iops_sec').fill('10000')
    await modal.locator('#iotune-write_iops_sec').fill('10000')
    await modal.locator('#iotune-read_iops_sec_max').fill('15000')
    await modal.locator('#iotune-write_iops_sec_max').fill('15000')
    await modal.locator('#iotune-read_iops_sec_max_length').fill('2')
    await modal.locator('#iotune-write_iops_sec_max_length').fill('2')
    await modal.locator('#iotune_kilobytes-size_iops_sec').fill('4')

    const createResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/item/qos_disk') && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await createResp).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    await expect(page.locator(`#table-qos-disk tbody tr:has-text("${name}")`).first())
      .toBeVisible({ timeout: 10000 })

    const saved = await findByName(apiv4Admin, 'qos_disk', name)
    expect(saved).not.toBeNull()
  })

  test('B2: edits a Disk QoS from row', async ({ authenticatedPage: page, apiv4Admin }, testInfo) => {
    const name = uniqueName(testInfo, 'qosdisk-edit')
    trackName(testInfo, 'qos_disk', name)

    await unwrap(
      adminQosDiskAdd({
        client: apiv4Admin,
        body: {
          name,
          description: 'before edit',
          allowed: { roles: false, categories: false, groups: false, users: false },
          iotune: {
            read_bytes_sec: 50 * 1024 * 1024,
            write_bytes_sec: 50 * 1024 * 1024,
            read_bytes_sec_max: 80 * 1024 * 1024,
            write_bytes_sec_max: 80 * 1024 * 1024,
            read_bytes_sec_max_length: 2,
            write_bytes_sec_max_length: 2,
            read_iops_sec: 10000,
            write_iops_sec: 10000,
            read_iops_sec_max: 15000,
            write_iops_sec_max: 15000,
            read_iops_sec_max_length: 2,
            write_iops_sec_max_length: 2,
            size_iops_sec: 4 * 1024,
          },
        },
      }),
    )

    await gotoResources(page)
    const row = page.locator(`#table-qos-disk tbody tr:has-text("${name}")`).first()
    await row.locator('button#btn-edit').click()

    const modal = page.locator('#modalQosDisk')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await modal.locator('#description').fill('after edit')
    await modal.locator('#iotune_megabytes-read_bytes_sec').fill('40')

    const editResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/item/qos_disk') && r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await editResp).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    await expect(row).toContainText('after edit', { timeout: 10000 })
  })

  test('B3: updates Disk QoS alloweds', async ({ authenticatedPage: page, apiv4Admin }, testInfo) => {
    const name = uniqueName(testInfo, 'qosdisk-alloweds')
    trackName(testInfo, 'qos_disk', name)

    await unwrap(
      adminTableInsert({
        client: apiv4Admin,
        path: { table: 'qos_disk' },
        body: {
          name,
          description: 'alloweds',
          allowed: { roles: false, categories: false, groups: false, users: false },
          iotune: {
            read_iops_sec: 1000,
            write_iops_sec: 1000,
          },
        },
      }),
    )

    await gotoResources(page)
    const row = page.locator(`#table-qos-disk tbody tr:has-text("${name}")`).first()
    await row.locator('button#btn-alloweds').click()
    await toggleAllowedsRolesAndSave(page, 'qos_disk')
  })

  test('B4: deletes Disk QoS from row', async ({ authenticatedPage: page, apiv4Admin }, testInfo) => {
    const name = uniqueName(testInfo, 'qosdisk-del')
    trackName(testInfo, 'qos_disk', name)

    await unwrap(
      adminTableInsert({
        client: apiv4Admin,
        path: { table: 'qos_disk' },
        body: {
          name,
          description: 'to delete',
          allowed: { roles: false, categories: false, groups: false, users: false },
          iotune: {
            read_iops_sec: 1000,
            write_iops_sec: 1000,
          },
        },
      }),
    )

    await gotoResources(page)
    const row = page.locator(`#table-qos-disk tbody tr:has-text("${name}")`).first()
    await row.locator('button#btn-delete').click()

    const delResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/item/table/qos_disk/') && r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await clickPnotifyButton(page, 'Ok')
    expect((await delResp).status()).toBeLessThan(400)
    await expect(row).toBeHidden({ timeout: 10000 })
  })

  test('C1-C4: creates interfaces for all kind dropdown values', async ({ authenticatedPage: page, apiv4Admin }, testInfo) => {
    const qosName = uniqueName(testInfo, 'qosnet-for-iface')
    trackName(testInfo, 'qos_net', qosName)

    await unwrap(
      adminTableInsert({
        client: apiv4Admin,
        path: { table: 'qos_net' },
        body: {
          name: qosName,
          description: 'for interfaces',
          allowed: { roles: false, categories: false, groups: false, users: false },
          bandwidth: {
            inbound: { '@average': 10000, '@peak': 15000, '@floor': 5000, '@burst': 20000 },
            outbound: { '@average': 10000, '@peak': 15000, '@burst': 20000 },
          },
        },
      }),
    )

    const qos = await findByName(apiv4Admin, 'qos_net', qosName)
    expect(qos?.id).toBeTruthy()

    const cases = [
      { kind: 'bridge', ifname: 'br-e2e0' },
      { kind: 'network', ifname: 'net-e2e0' },
      { kind: 'ovs', ifname: '100' },
      { kind: 'personal', ifname: '2000-2001' },
    ]

    await gotoResources(page)

    for (const c of cases) {
      const name = uniqueName(testInfo, `iface-${c.kind}`)
      trackName(testInfo, 'interfaces', name)

      await page.locator('.add-new-interface').click()
      const modal = page.locator('#modalInterfaces')
      await modal.waitFor({ state: 'visible', timeout: 10000 })

      await modal.locator('#name').fill(name)
      await modal.locator('#description').fill(`iface ${c.kind}`)
      await modal.locator('#kind').selectOption(c.kind)
      await modal.locator('#ifname').fill(c.ifname)
      await modal.locator('#model').selectOption('virtio')
      await modal.locator('#qos_id').selectOption(String(qos.id))

      const createResp = page.waitForResponse(
        (r) => r.url().includes('/api/v4/admin/item/table/add/interfaces') && r.request().method() === 'POST',
        { timeout: 15000 },
      )
      await modal.locator('#send').click()
      expect((await createResp).status()).toBeLessThan(400)
      await modal.waitFor({ state: 'hidden', timeout: 10000 })

      await expect(page.locator(`#table-interfaces tbody tr:has-text("${name}")`).first())
        .toBeVisible({ timeout: 10000 })
    }
  })

  test('C5/C6/C7: edit, alloweds and delete interface', async ({ authenticatedPage: page, apiv4Admin }, testInfo) => {
    const name = uniqueName(testInfo, 'iface-crud')
    trackName(testInfo, 'interfaces', name)

    await unwrap(
      adminTableInsert({
        client: apiv4Admin,
        path: { table: 'interfaces' },
        body: {
          name,
          description: 'before edit',
          kind: 'bridge',
          net: 'br-e2e-crud',
          model: 'virtio',
          qos_id: 'unlimited',
          allowed: { roles: false, categories: false, groups: false, users: false },
        },
      }),
    )

    await gotoResources(page)
    const row = page.locator(`#table-interfaces tbody tr:has-text("${name}")`).first()
    await expect(row).toBeVisible({ timeout: 10000 })

    // Edit
    await row.locator('button#btn-edit').click()
    const modal = page.locator('#modalInterfaces')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await modal.locator('#description').fill('after edit')
    await modal.locator('#ifname').fill('br-e2e-crud-edit')
    await modal.locator('#send').click()
    await modal.waitFor({ state: 'hidden', timeout: 10000 })
    await expect(row).toContainText('after edit', { timeout: 10000 })

    // Alloweds
    await row.locator('button#btn-alloweds').click()
    await toggleAllowedsRolesAndSave(page, 'interfaces')

    // Delete
    await row.locator('button#btn-delete').click()
    const delResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/item/table/interfaces/') && r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await clickPnotifyButton(page, 'Ok')
    expect((await delResp).status()).toBeLessThan(400)
    await expect(row).toBeHidden({ timeout: 10000 })
  })

  test('D1/D2: create video and update alloweds', async ({ authenticatedPage: page }, testInfo) => {
    const name = uniqueName(testInfo, 'video')
    trackName(testInfo, 'videos', name)

    await gotoResources(page)
    await page.locator('.add-new-videos').click()

    const modal = page.locator('#modalVideos')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await modal.locator('#name').fill(name)
    await modal.locator('#description').fill('video create')
    await modal.locator('#model').selectOption('qxl')

    const createResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/item/table/add/videos') && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await createResp).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    const row = page.locator(`#videos tbody tr:has-text("${name}")`).first()
    await expect(row).toBeVisible({ timeout: 10000 })

    await row.locator('button#btn-alloweds').click()
    await toggleAllowedsRolesAndSave(page, 'videos')
  })

  test('E1: updates alloweds for an existing boot row', async ({ authenticatedPage: page }) => {
    await gotoResources(page)
    const row = page.locator('#boots tbody tr:not(.dataTables_empty)').first()
    await expect(row).toBeVisible({ timeout: 10000 })
    await row.locator('button#btn-alloweds').click()
    await toggleAllowedsRolesAndSave(page, 'boots')
  })

  test('F1/F3/F4: remote VPN create, alloweds and delete (no edit button in current UI)', async ({ authenticatedPage: page }, testInfo) => {
    const name = uniqueName(testInfo, 'vpn')

    await gotoResources(page)
    await page.locator('.add-new-remotevpn').click()
    const modal = page.locator('#modalRemotevpn')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    await modal.locator('#name').fill(name)
    await modal.locator('#description').fill('vpn created')

    const createResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/item/table/add/remotevpn') && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await createResp).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    const row = page.locator(`#table-remotevpn tbody tr:has-text("${name}")`).first()
    await expect(row).toBeVisible({ timeout: 10000 })
    await expect(row.locator('button#btn-edit')).toHaveCount(0)

    // Alloweds
    await row.locator('button#btn-alloweds').click()
    await toggleAllowedsRolesAndSave(page, 'remotevpn')

    // Delete
    await row.locator('button#btn-delete').click()
    const delResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/item/table/remotevpn/') && r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await clickPnotifyButton(page, 'Ok')
    expect((await delResp).status()).toBeLessThan(400)
    await expect(row).toBeHidden({ timeout: 10000 })
  })

  test.skip('F5: remote VPN download hits API successfully', async ({ authenticatedPage: page }) => {
    await gotoResources(page)
    const row = page.locator('#table-remotevpn tbody tr:not(.dataTables_empty)').first()
    await expect(row).toBeVisible({ timeout: 10000 })

    const downloadResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/remote_vpn/') && r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await row.locator('button#btn-download').click()
    expect((await downloadResp).status()).toBeLessThan(400)
  })

  test('G1/G2: bastion status reflects cfg enabled/disabled state', async ({ authenticatedPage: page, apiv4Admin }) => {
    const cfg = await unwrap(getAdminBastionConfig({ client: apiv4Admin })).catch(() => null)
    await gotoResources(page)

    const allowedsBtn = page.locator('#BastionConfig #btn-alloweds')
    const editBtn = page.locator('#BastionConfig #btn-edit-bastion')
    const deleteBtn = page.locator('#BastionConfig #btn-delete-disallowed')

    if (cfg?.bastion_enabled_in_cfg === true) {
      await expect(page.locator('#BastionConfig #bastionStatusLabel')).toContainText(/enabled in cfg/i)
      await expect(allowedsBtn).toBeVisible()
      await expect(editBtn).toBeVisible()
      await expect(deleteBtn).toBeVisible()
    } else {
      await expect(page.locator('#BastionConfig #bastionStatusLabel')).toContainText(/disabled in cfg/i)
      await expect(allowedsBtn).toBeHidden()
      await expect(editBtn).toBeHidden()
      await expect(deleteBtn).toBeHidden()
    }
  })

  test('G3: edits bastion config form when cfg is enabled', async ({ authenticatedPage: page, apiv4Admin }) => {
    const cfg = await unwrap(getAdminBastionConfig({ client: apiv4Admin })).catch(() => null)
    test.skip(!cfg?.bastion_enabled_in_cfg, 'Bastion disabled in cfg for this environment')

    await gotoResources(page)
    await page.locator('#BastionConfig #btn-edit-bastion').click()

    const modal = page.locator('#modalEditBastion')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    const currentDomain = await modal.locator('#bastion-domain').inputValue()
    await modal.locator('#bastion-domain').fill(currentDomain)

    const putResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/item/config/bastion') && r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await putResp).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })
  })

  test('G6/G7: delete-disallowed bastion targets cancel then confirm', async ({ authenticatedPage: page, apiv4Admin }) => {
    const cfg = await unwrap(getAdminBastionConfig({ client: apiv4Admin })).catch(() => null)
    test.skip(!cfg?.bastion_enabled_in_cfg, 'Bastion disabled in cfg for this environment')

    await gotoResources(page)

    // Cancel path
    let deleteFired = false
    page.on('request', (req) => {
      if (req.url().includes('/api/v4/admin/items/bastion/disallowed') && req.method() === 'DELETE') {
        deleteFired = true
      }
    })
    await page.locator('#BastionConfig #btn-delete-disallowed').click()
    await clickPnotifyButton(page, 'Cancel')
    expect(deleteFired).toBeFalsy()

    // Confirm path
    await page.locator('#BastionConfig #btn-delete-disallowed').click()
    const delResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/items/bastion/disallowed') && r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await clickPnotifyButton(page, 'Delete')
    expect((await delResp).status()).toBeLessThan(400)
  })

  test('H1/H2: lists virt_install entries and opens XML editor', async ({ authenticatedPage: page }) => {
    const listResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/items/table/virt_install') && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await gotoResources(page)
    expect((await listResp).status()).toBeLessThan(400)

    const row = page.locator('#table-virt-install tbody tr:not(.dataTables_empty)').first()
    await expect(row).toBeVisible({ timeout: 10000 })

    await row.locator('button#btn-xml').click()
    const xmlModal = page.locator('#modalEditXmlSections')
    await xmlModal.waitFor({ state: 'visible', timeout: 10000 })
    await expect(xmlModal.locator('#xmlSectionsContainer')).toBeVisible()
  })
})
