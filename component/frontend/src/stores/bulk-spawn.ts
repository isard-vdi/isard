import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { WsBulkSpawnFailure } from '@/types/ws-events'

export interface BulkSpawnResult {
  created: number
  failed: number
  failures: WsBulkSpawnFailure[]
}

export const useBulkSpawnStore = defineStore('bulk-spawn', () => {
  const deploymentsInProgress = ref<Set<string>>(new Set())
  // Outcome of the last finished bulk create per deployment.
  const results = ref<Map<string, BulkSpawnResult>>(new Map())

  const isInProgress = (deploymentId: string) =>
    computed(() => deploymentsInProgress.value.has(deploymentId))

  const resultFor = (deploymentId: string) => computed(() => results.value.get(deploymentId))

  const start = (deploymentId: string) => {
    deploymentsInProgress.value = new Set([...deploymentsInProgress.value, deploymentId])
    // A fresh run supersedes any previous outcome.
    if (results.value.has(deploymentId)) {
      const next = new Map(results.value)
      next.delete(deploymentId)
      results.value = next
    }
  }

  const end = (deploymentId: string, result?: BulkSpawnResult) => {
    if (result) {
      results.value = new Map(results.value).set(deploymentId, result)
    }
    if (deploymentsInProgress.value.has(deploymentId)) {
      const next = new Set(deploymentsInProgress.value)
      next.delete(deploymentId)
      deploymentsInProgress.value = next
    }
  }

  const clearResult = (deploymentId: string) => {
    if (!results.value.has(deploymentId)) return
    const next = new Map(results.value)
    next.delete(deploymentId)
    results.value = next
  }

  const $reset = () => {
    deploymentsInProgress.value = new Set()
    results.value = new Map()
  }

  return {
    deploymentsInProgress,
    results,
    isInProgress,
    resultFor,
    start,
    end,
    clearResult,
    $reset
  }
})
