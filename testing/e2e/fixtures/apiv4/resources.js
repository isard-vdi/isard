// Registry-driven resource tracking + ordered teardown. Domain modules
// (desktops.js, bookings.js, reservables.js) register their kind here, so
// adding a resource type never touches this file.

/** @typedef {(client: unknown, id: string) => Promise<unknown>} Deleter */

// kind -> { order, delete }. Lower `order` is torn down first — bookings
// reference plans, plans reference desktops/gpus.
const registry = new Map()

/** @param {string} kind @param {{ order: number, delete: Deleter }} spec */
export function registerResource(kind, spec) {
  registry.set(kind, spec)
}

export function track(testInfo, kind, id) {
  testInfo.annotations.push({ type: kind, description: id })
}

export async function cleanupTrackedResources(client, testInfo) {
  const ordered = [...registry.entries()].sort((a, b) => a[1].order - b[1].order)
  for (const [kind, spec] of ordered) {
    const ids = testInfo.annotations
      .filter((a) => a.type === kind)
      .map((a) => a.description)
    for (const id of ids) {
      await spec.delete(client, id).catch(() => {})
    }
  }
}
