// vue-cal opens on the current Monday-first week; a window a few hours ahead on a
// Sunday evening lands on the next week, which is not drawn at all.

/** Whole weeks between the Monday of `startMs` and the Monday of `nowMs`. */
export function weeksAhead(startMs, nowMs = Date.now()) {
  const mondayOf = (ms) => {
    const d = new Date(ms)
    d.setHours(0, 0, 0, 0)
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7))
    return d.getTime()
  }
  return Math.round((mondayOf(startMs) - mondayOf(nowMs)) / (7 * 24 * 60 * 60 * 1000))
}

/** Click forward until the week holding `startMs` is the one on screen. */
export async function showWeekOf(page, startMs) {
  for (let i = 0; i < weeksAhead(startMs); i++) {
    const refetch = page.waitForResponse(
      (r) => /\/api\/v4\/item\/reservables-planner\/by-item\//.test(r.url()),
      { timeout: 15000 },
    )
    await page.locator('#vuecal .vuecal__arrow--next').first().click()
    await refetch
  }
}
