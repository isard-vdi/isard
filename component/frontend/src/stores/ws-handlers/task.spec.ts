import { QueryClient } from '@tanstack/vue-query'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useStorageTasksStore } from '@/stores/storage-tasks'
import { taskEventHandlers } from './task'

describe('task event', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('keeps the latest state of each task, merged over the previous one', () => {
    const queryClient = new QueryClient()
    taskEventHandlers.task(
      queryClient,
      JSON.stringify({ id: 't1', status: 'queued', effective_position: 3 })
    )
    taskEventHandlers.task(
      queryClient,
      JSON.stringify({ id: 't1', status: 'started', progress: 0.5 })
    )
    expect(useStorageTasksStore().tasks.t1).toEqual({
      id: 't1',
      status: 'started',
      effective_position: 3,
      progress: 0.5
    })
  })

  it('ignores a payload without an id', () => {
    taskEventHandlers.task(new QueryClient(), JSON.stringify({ status: 'finished' }))
    expect(useStorageTasksStore().tasks).toEqual({})
  })
})
