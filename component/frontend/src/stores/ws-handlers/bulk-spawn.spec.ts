import { QueryClient } from '@tanstack/vue-query'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useBulkSpawnStore } from '@/stores/bulk-spawn'
import { bulkSpawnEventHandlers } from './bulk-spawn'

const qc = new QueryClient()

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('end_creating_desktops', () => {
  it('records the failed desktops so the modal can warn', () => {
    const store = useBulkSpawnStore()
    bulkSpawnEventHandlers.creating_desktops(qc, JSON.stringify({ deployment_id: 'dep-1' }))
    expect(store.deploymentsInProgress.has('dep-1')).toBe(true)

    bulkSpawnEventHandlers.end_creating_desktops(
      qc,
      JSON.stringify({
        deployment_id: 'dep-1',
        created: 1,
        failed: 2,
        failures: [
          { name: 'a', description_code: 'template_not_ready' },
          { name: 'b', description_code: 'template_not_ready' }
        ]
      })
    )

    expect(store.deploymentsInProgress.has('dep-1')).toBe(false)
    const result = store.results.get('dep-1')
    expect(result?.created).toBe(1)
    expect(result?.failed).toBe(2)
    expect(result?.failures.map((f) => f.name)).toEqual(['a', 'b'])
    expect(result?.failures[0].description_code).toBe('template_not_ready')
  })

  it('tolerates an old payload with only deployment_id (no outcome recorded)', () => {
    const store = useBulkSpawnStore()
    bulkSpawnEventHandlers.creating_desktops(qc, JSON.stringify({ deployment_id: 'dep-2' }))
    bulkSpawnEventHandlers.end_creating_desktops(qc, JSON.stringify({ deployment_id: 'dep-2' }))

    expect(store.deploymentsInProgress.has('dep-2')).toBe(false)
    expect(store.results.get('dep-2')).toBeUndefined()
  })

  it('a fresh run supersedes a previous outcome', () => {
    const store = useBulkSpawnStore()
    store.end('dep-3', { created: 0, failed: 1, failures: [{ name: 'x' }] })
    expect(store.results.get('dep-3')?.failed).toBe(1)

    store.start('dep-3')
    expect(store.results.get('dep-3')).toBeUndefined()
  })
})
