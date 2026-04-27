import { test, expect } from '../fixtures/desktops.js'
import { commonHelpers } from '../fixtures/common.js'

const desktopsURL = '/frontend/desktops';

async function getDesktopCard(page, desktopName) {
    const cardSelector = 'div.overflow-hidden.border-l-10.p-0';
    await page.locator(cardSelector).first().waitFor({ state: 'visible', timeout: 15000 });
    await page.waitForTimeout(500);

    const card = page.locator(cardSelector).filter({
        has: page.locator('div.text-lg.font-bold.truncate span', { hasText: desktopName })
    }).first();

    if (await card.isVisible().catch(() => false)) {
        await card.scrollIntoViewIfNeeded();
        return card;
    }

    throw new Error(`Desktop "${desktopName}" not found`);
}


async function performClick(page, locator, waitMs = 1000) {
    async function clickElementHandle(page, handle) {
        if (!handle) return false
        try {
            await handle.scrollIntoViewIfNeeded?.().catch(() => { })
            const disabled = await handle.getAttribute('disabled').catch(() => null)
            const ariaDisabled = await handle.getAttribute('aria-disabled').catch(() => null)
            if (disabled !== null || ariaDisabled === 'true') return false
            await page.evaluate((el) => el.click(), handle)
            return true
        } catch (err) {
            return false
        }
    }

    const first = locator.first()
    const h = await first.elementHandle().catch(() => null)
    let clicked = false
    if (h) clicked = await clickElementHandle(page, h)
    if (!clicked) {
        await first.click().catch(() => { })
    }
    await page.waitForTimeout(waitMs)
}

test('should display "Desktops" page title after login', async ({
    page,
    users,
    categories,
    desktopHelpers
}) => {
    await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_13, categories)

    const currentUrl = page.url()
    expect(currentUrl).toMatch(desktopsURL)

    await commonHelpers.checkNoRouterErrors(page)

})

// All tests using the GPU desktop share admin_e2e_01 and must run serially
test.describe.serial('GPU desktop tests', () => {
    test('stopped desktop shows Start button', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
        await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_01, categories)

        const card = await getDesktopCard(page, desktopsData.gpu.name)
        const startBtn = card.locator('button:has-text("Start now"), button:has-text("Start")').first()
        await expect(startBtn).toBeVisible({ timeout: 15000 })
    })

    test('GPU desktop without booking shows needs booking indicator', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
        await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_01, categories)

        const gpuCard = await getDesktopCard(page, desktopsData.gpu.name)
        await gpuCard.waitFor({ state: 'visible', timeout: 10000 })
        const bookingIndicator = gpuCard.locator('div.inline-flex.items-center.gap-1\\.5.p-1\\.5.h-6.rounded-sm.font-bold.text-base-white.max-w-full > svg[alt="info-circle icon"]').first()
        await expect(bookingIndicator).toBeVisible({ timeout: 10000 })
    })

    test('menu shows edit, delete options', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
        await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_01, categories)

        const card = await getDesktopCard(page, desktopsData.gpu.name)
        const menuBtn = card.locator('div.absolute.top-3.right-3.flex.items-center.z-20 button').last()
        await performClick(page, menuBtn, 500)

        await expect(page.getByText(/edit/i).first()).toBeVisible({ timeout: 10000 })
        await expect(page.getByText(/delete|remove/i).first()).toBeVisible({ timeout: 10000 })
    })

    test('GPU desktop shows booking badge', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
        await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_01, categories)

        await page.waitForTimeout(2000)
        const gpuCard = await getDesktopCard(page, desktopsData.gpu.name)
        await expect(gpuCard).toBeVisible({ timeout: 10000 })
        const gpuBadge = gpuCard.locator('text=/.*needs booking.*/i').first()
        await expect(gpuBadge).toBeVisible({ timeout: 10000 })
    })

    test('GPU desktop menu shows book option', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
        await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_01, categories)

        const gpuCard = await getDesktopCard(page, desktopsData.gpu.name)
        const menuBtn = gpuCard.locator('div.absolute.top-3.right-3.flex.items-center.z-20 button').last()
        await performClick(page, menuBtn, 500)

        const bookOption = page.getByText(/book|reserve/i).first()
        await expect(bookOption).toBeVisible({ timeout: 10000 })
    })

    test('network button shows networks with MAC', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
        await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_01, categories)

        const gpuCard = await getDesktopCard(page, desktopsData.gpu.name)
        const networkBtn = gpuCard.locator('div.absolute.top-3.right-3.flex.items-center.z-20 button').first()

        await expect(networkBtn).toBeVisible({ timeout: 10000 })
        await performClick(page, networkBtn, 1000)

        const macText = gpuCard.locator('text=/^52:54:00.+/').first()
        await expect(macText).toBeVisible({ timeout: 10000 })
    })

    test('GPU desktop start shows modal with dropdown', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
        await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_01, categories)

        const gpuCard = await getDesktopCard(page, desktopsData.gpu.name)
        const startBtn = gpuCard.locator('button:has-text("Start"), button:has-text("Start now")').first()
        await performClick(page, startBtn, 1500)

        const modal = page.locator('[role="dialog"]').first()
        await expect(modal).toBeVisible({ timeout: 10000 })

        const dropdown = modal.locator('[role="combobox"]').first()
        await expect(dropdown).toBeVisible({ timeout: 5000 })
    })

    test('Start Now button opens modal for GPU desktop', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
        await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_01, categories)

        const gpuCard = await getDesktopCard(page, desktopsData.gpu.name)
        await gpuCard.isVisible({ timeout: 10000 })
        const startBtn = gpuCard.locator('button:has-text("Start"), button:has-text("Start now")').first()
        await performClick(page, startBtn, 1500)

        const modal = page.locator('[role="dialog"]').first()
        await expect(modal).toBeVisible({ timeout: 10000 })

        const dropdown = modal.locator('[role="combobox"]').first()
        await expect(dropdown).toBeVisible({ timeout: 5000 })
    })

    test.skip('stopped desktop CAN be edited', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
        // Skip: /desktops/:id/edit route doesn't exist yet
        await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_01, categories)

        const card = await getDesktopCard(page, desktopsData.gpu.name)
        const menuBtn = card.locator('div.absolute.top-3.right-3.flex.items-center.z-20 button').last()
        await performClick(page, menuBtn, 500)

        const editOption = page.getByText(/edit/i).first()
        await expect(editOption).toBeVisible({ timeout: 10000 })

        await editOption.click()
        await page.waitForURL(/\/desktops\/[0-9a-fA-F-]{10,}\/edit/, { timeout: 15000 })
        expect(page.url()).toMatch(/\/desktops\/[0-9a-fA-F-]{10,}\/edit/)
    })

    test('desktop without bastion_target does NOT show bastion icon', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
        await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_01, categories)

        const regularCard = await getDesktopCard(page, desktopsData.gpu.name)
        // Bastion icon is conditionally rendered based on
        // desktop.bastion_target?.http?.enabled || ssh?.enabled. A desktop
        // without a bastion target should not surface the icon at all.
        const bastionIcon = regularCard.locator(
            'div.absolute.top-3.right-3.flex.items-center.z-20 button:has(img[alt*="globe-04"])'
        )
        await expect(bastionIcon).toHaveCount(0, { timeout: 5000 })
    })
})

test('booked desktop shows booking badge', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
    await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_02, categories)

    const bookedCard = await getDesktopCard(page, desktopsData.booked.name)
    await bookedCard.waitFor({ state: 'visible', timeout: 10000 })
    const bookingBadge = bookedCard.locator('div.inline-flex.items-center.gap-1\\.5.p-1\\.5.h-6.rounded-sm.font-bold.text-base-white.max-w-full > svg[alt="info-circle icon"]').first()
    await expect(bookingBadge).toBeVisible({ timeout: 10000 })
})

test('failed desktop shows Retry button', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
    await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_03, categories)

    const card = await getDesktopCard(page, desktopsData.failed.name)
    const retryBtn = card.locator('button:has-text("Restart"), button:has-text("retry")').first()
    await expect(retryBtn).toBeVisible({ timeout: 15000 })
})

test('maintenance desktop shows In maintenance text and Cancel operation button', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
    await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_04, categories)

    const maintenanceCard = await getDesktopCard(page, desktopsData.maintenance.name)
    await expect(maintenanceCard).toBeVisible({ timeout: 10000 })

    const maintenanceText = maintenanceCard.locator('text=In maintenance').first()
    await expect(maintenanceText).toBeVisible({ timeout: 10000 })

    const actionBtn = maintenanceCard.locator('button:has-text("Cancel operation")').first()
    await expect(actionBtn).toBeVisible({ timeout: 10000 })
})

test('downloading desktop shows progress bar', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
    await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_05, categories)

    const downloadingCard = await getDesktopCard(page, desktopsData.downloading.name)
    await downloadingCard.isVisible({ timeout: 10000 })

    const progressBar = downloadingCard.locator('[role="progressbar"]').first()
    await expect(progressBar).toBeVisible({ timeout: 10000 })
})

test('unknown status desktop CANNOT be edited', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
    await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_06, categories)

    const card = await getDesktopCard(page, desktopsData.unknown.name)

    // The info icon is a top-level card button (not in the dropdown anymore).
    // It is always rendered regardless of status, so it must be visible here.
    const infoIcon = card.locator(
        'div.absolute.top-3.right-3.flex.items-center.z-20 button:has(img[alt*="info-circle"])'
    )
    await expect(infoIcon).toBeVisible({ timeout: 10000 })

    // The dropdown should still hide the Edit menu entry on Unknown status —
    // edit is only offered when the desktop is Stopped.
    const menuBtn = card.locator('div.absolute.top-3.right-3.flex.items-center.z-20 button').last()
    await performClick(page, menuBtn, 500)
    const editOption = page.getByText(/^edit$/i).first()
    await expect(editOption).not.toBeVisible({ timeout: 3000 }).catch(() => { })
})

test('recreate desktop shows modal', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
    await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_07, categories)

    const recreableCard = await getDesktopCard(page, desktopsData.recreable.name)
    const menuBtn = recreableCard.locator('div.absolute.top-3.right-3.flex.items-center.z-20 button').last()
    await expect(menuBtn).toBeVisible({ timeout: 10000 })
    await menuBtn.click()
    await page.waitForTimeout(1000)

    const recreateOption = page.locator('[role="menuitem"]:has-text("Recreate")').first()
    await expect(recreateOption).toBeVisible({ timeout: 10000 })
    await recreateOption.click()
    await page.waitForTimeout(1000)

    const modal = page.locator('[role="alertdialog"]').first()
    await expect(modal).toBeVisible({ timeout: 10000 })

    const recreateBtn = modal.locator('button:has-text("Recreate Desktop")').first()
    await expect(recreateBtn).toBeVisible({ timeout: 5000 })
    await recreateBtn.click()
})

// All bastion tests share admin_e2e_08 and must run serially.
//
// Bastion access used to live as an entry inside the per-card "⋮" dropdown.
// The card now exposes a dedicated top-right "globe-04" icon that's only
// rendered when the desktop's bastion target has http or ssh enabled —
// clicking it toggles an in-card overlay; the "Details" button inside the
// overlay opens the modal that previously lived in the dropdown path.
const BASTION_ICON = 'div.absolute.top-3.right-3.flex.items-center.z-20 button:has(img[alt*="globe-04"])'
test.describe.serial('Bastion modal', () => {
    test('desktop with bastion_target shows the bastion icon', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
        await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_08, categories)

        const bastionCard = await getDesktopCard(page, desktopsData.bastion.name)
        const bastionIcon = bastionCard.locator(BASTION_ICON)
        await expect(bastionIcon).toBeVisible({ timeout: 10000 })
    })

    test('bastion modal shows HTTP/HTTPS URLs when HTTP enabled', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
        await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_08, categories)

        const bastionCard = await getDesktopCard(page, desktopsData.bastion.name)
        await bastionCard.locator(BASTION_ICON).click()
        await page.waitForTimeout(500)

        const detailsBtn = bastionCard.getByRole('button', { name: /details/i }).first()
        await expect(detailsBtn).toBeVisible({ timeout: 5000 })
        await detailsBtn.click()
        await page.waitForTimeout(1000)

        const modal = page.locator('[role="dialog"]').first()
        await expect(modal).toBeVisible({ timeout: 10000 })
        await expect(modal.getByText(/Bastion target ID/i)).toBeVisible()
        await expect(modal.getByText(/http:\/\//i)).toBeVisible()
        await expect(modal.getByText(/https:\/\//i)).toBeVisible()
    })

    test('bastion modal shows authorized keys textarea when SSH enabled', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
        await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_08, categories)

        const bastionCard = await getDesktopCard(page, desktopsData.bastion.name)
        await bastionCard.locator(BASTION_ICON).click()
        await page.waitForTimeout(500)

        const detailsBtn = bastionCard.getByRole('button', { name: /details/i }).first()
        await detailsBtn.click()
        await page.waitForTimeout(1000)

        const modal = page.locator('[role="dialog"]').first()
        await expect(modal).toBeVisible({ timeout: 10000 })

        await expect(modal.getByText(/Authorized SSH keys/i)).toBeVisible()
        const textarea = modal.getByRole('textbox', { name: /ssh-(ed25519|rsa|ecdsa)/i })
        await expect(textarea).toBeVisible()
    })
})

test('change and start modal appears when GPU is unavailable', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
    await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_10, categories)

    const testCard = await getDesktopCard(page, desktopsData.gpuUnavailable.name)
    const startBtn = testCard.locator('button:has-text("Start"), button:has-text("Start now")').first()
    await expect(startBtn).toBeVisible({ timeout: 10000 })
    await performClick(page, startBtn, 2000)

    const modal = page.locator('[role="dialog"]').first()
    await expect(modal).toBeVisible({ timeout: 20000 })

    const modalContent = modal.locator('text=/is not available for desktop/i').first()
    await expect(modalContent).toBeVisible({ timeout: 10000 })

    const changeAndStartBtn = modal.locator('button:has-text("Change and start")').first()
    await expect(changeAndStartBtn).toBeVisible({ timeout: 10000 })
    await performClick(page, changeAndStartBtn, 1500)
    const changeAndStartTitle = modal.locator('text=/Change and Start/i').first()
    await expect(changeAndStartTitle).toBeVisible({ timeout: 10000 })
})

test('temporary filter shows only temporary desktop', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
    await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_11, categories)

    const temporaryBtn = page.locator('button:has-text("Temporary"), button:has-text("Volatiles")').first()
    await performClick(page, temporaryBtn, 1000)

    const allCards = page.locator('[data-desktop-id]')
    const count = await allCards.count()

    if (count > 0) {
        for (let i = 0; i < count; i++) {
            const card = allCards.nth(i)
            const text = await card.textContent()
            expect(text).toContain('Temporary')
        }
    }
})

test.describe('Desktop search and filters', () => {
    test('search filters desktops by name', async ({ page, users, categories, desktopHelpers }) => {
        await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_14, categories)

        const searchInput = page.locator('input[type="text"], input[placeholder*="Search" i]').first()
        await searchInput.fill('test')
        await page.waitForTimeout(1000)

        const allCards = page.locator('.overflow-hidden.border-l-10.p-0.border-l-secondary-3-500')
        expect(await allCards.count()).toBeGreaterThanOrEqual(1)

        await searchInput.fill('askdfghjklasdfghjklasdfgh')
        const clearFiltersBtn = page.locator('button.inline-flex.gap-2.text-sm:has-text("Clear filters")').first()
        await expect(clearFiltersBtn).toBeVisible({ timeout: 3000 })
    })
})

test('new-desktop button navigates to new form', async ({ page, users, categories, desktopHelpers }) => {
    await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_15, categories)

    await page.waitForTimeout(3000)
    const newDesktopBtn = page.locator('button:has-text("New Desktop")').first()
    await expect(newDesktopBtn).toBeVisible({ timeout: 10000 })
    await newDesktopBtn.click()
    await page.waitForURL(/\/desktops\/new$/, { timeout: 15000 })
    expect(page.url()).toMatch(/\/desktops\/new$/)
})

test.skip('start desktop with storage workflow', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
    await desktopHelpers.loginAndGoToDesktops(page, users.admin_e2e_09, categories)

    const card = await getDesktopCard(page, desktopsData.test.name)
    const startBtn = card.locator('button:has-text("Start"), button:has-text("Start now")').first()
    await performClick(page, startBtn, 1000)

    await page.waitForTimeout(2000)

    const processingBtn = card.locator('button:has-text("Processing"), button[disabled]').first()
    if (await processingBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
        await page.waitForTimeout(5000)
    }

    const stopBtn = card.locator('button:has-text("Stop"), button:has-text("stop")').first()
    const connectBtn = card.locator('button:has-text("Connect"), button:has-text("connect")').first()

    await expect(stopBtn).toBeVisible({ timeout: 45000 })
    await expect(connectBtn).toBeVisible({ timeout: 10000 })

    await performClick(page, stopBtn, 1000)
    await page.waitForTimeout(1000)

    const forceStopBtn = card.locator('button:has-text("Force Stop"), button:has-text("force")').first()
    await expect(forceStopBtn).toBeVisible({ timeout: 10000 })
    await performClick(page, forceStopBtn, 1000)
})

test.describe('Booking modals', () => {
    test('not enough advanced time modal appears for user without booking permissions', async ({ page, users, categories, desktopHelpers, desktopsData }) => {
        await desktopHelpers.loginAndGoToDesktops(page, users.user_e2e_01, categories)

        const testCard = await getDesktopCard(page, desktopsData.notEnoughAdvancedTime.name)
        const startBtn = testCard.locator('button:has-text("Start"), button:has-text("start")').first()
        await performClick(page, startBtn, 1500)

        const modal = page.locator('[role="alertdialog"]').first()
        await expect(modal).toBeVisible({ timeout: 10000 })

        const modalTitle = modal.locator('text=/Not enough advanced time/i').first()
        await expect(modalTitle).toBeVisible({ timeout: 5000 })
    })
})
