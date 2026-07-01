// @ts-check
// Regression test for the lab-options checkbox state-desync bug on the admin
// interfaces modal. The checkboxes are wrapped by iCheck which renders an
// overlay over each native input — touching only the native input via
// `.prop('checked', ...)` leaves the overlay visually checked while the form
// value is false. The fix routes all programmatic resets through
// `.iCheck('uncheck').iCheck('update')` and binds them to show.bs.modal /
// hidden.bs.modal so every modal session starts clean.
import { test, expect } from '../navbar'
import { PageAdminResources } from './resources-page'

test.describe('LabOptsCheckbox', () => {
  test('lab option checkbox is unchecked after close+reopen of the create modal', async ({ page, administration }) => {
    test.setTimeout(120000)

    const resources = new PageAdminResources(page)
    await resources.goto()

    const modal = page.locator('#modalInterfaces')
    const rowLabOpts = page.locator('#row_lab_opts')
    const checkbox = page.locator('#modalInterfaces #lab_mac_spoofing')

    // The lab-options controls only exist for OVS-family kinds. Skip if the
    // interfaces modal doesn't expose the `ovs` kind on this stack (unseeded
    // resources fixture) — same guard style as resources.spec.js.
    await page.locator('a').filter({ hasText: 'Add new' }).first().click()
    await expect(modal).toBeVisible()
    const hasOvs = await page
      .locator('#modalInterfaces #kind option[value="ovs"]')
      .count()
      .catch(() => 0)
    test.skip(
      !hasOvs,
      'Admin interfaces modal has no ovs kind on this stack — bring up with USAGE=test or seed the resources fixture'
    )

    // Round 1: pick ovs, tick the iCheck overlay, close via Cancel.
    await page.locator('#modalInterfaces #kind').selectOption('ovs')
    await expect(rowLabOpts).toBeVisible()

    // Click the iCheck overlay (the visible part). .check() on the native
    // input would fail because iCheck hides it with opacity:0.
    await page.locator('#row_lab_opts label:has(#lab_mac_spoofing) .iCheck-helper').click()
    expect(await checkbox.isChecked()).toBe(true)

    await page.locator('#modalInterfaces button.btn-secondary[data-dismiss="modal"]').click()
    await expect(modal).toBeHidden()

    // Round 2: open again, pick ovs again, the checkbox MUST be unchecked
    // and the iCheck wrapper MUST not carry the prior `checked` class.
    await page.locator('a').filter({ hasText: 'Add new' }).first().click()
    await expect(modal).toBeVisible()
    await page.locator('#modalInterfaces #kind').selectOption('ovs')
    await expect(rowLabOpts).toBeVisible()

    expect(await checkbox.isChecked()).toBe(false)
    const iCheckHasCheckedClass = await page.evaluate(
      () => !!document.querySelector('#row_lab_opts label:has(#lab_mac_spoofing) .icheckbox_flat-green.checked')
    )
    expect(iCheckHasCheckedClass).toBe(false)
  })
})
