import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { WsUserMigrationPayload } from '@/types/ws-events'

export type MigrationKind = 'desktops' | 'templates' | 'media' | 'deployments'
export type MigrationKindState = 'pending' | 'in_progress' | 'done' | 'error'

export const useUserMigrationStore = defineStore('user-migration', () => {
  const progress = ref<WsUserMigrationPayload | null>(null)

  const status = computed(() => progress.value?.status ?? null)
  const isMigrating = computed(() => status.value === 'migrating')
  const isDone = computed(() => status.value === 'migrated')
  const isFailed = computed(() => status.value === 'failed')

  const kindState = (kind: MigrationKind): MigrationKindState => {
    const p = progress.value
    if (!p) return 'pending'
    if (p[`migrated_${kind}_error`]) return 'error'
    if (p[`migrated_${kind}`] === true) return 'done'
    return isMigrating.value ? 'in_progress' : 'pending'
  }

  const update = (payload: WsUserMigrationPayload) => {
    progress.value = payload
  }

  const $reset = () => {
    progress.value = null
  }

  return {
    progress,
    status,
    isMigrating,
    isDone,
    isFailed,
    kindState,
    update,
    $reset
  }
})
