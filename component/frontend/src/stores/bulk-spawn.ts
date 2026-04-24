import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export const useBulkSpawnStore = defineStore('bulk-spawn', () => {
  const deploymentsInProgress = ref<Set<string>>(new Set())

  const isInProgress = (deploymentId: string) =>
    computed(() => deploymentsInProgress.value.has(deploymentId))

  const start = (deploymentId: string) => {
    deploymentsInProgress.value = new Set([...deploymentsInProgress.value, deploymentId])
  }

  const end = (deploymentId: string) => {
    if (!deploymentsInProgress.value.has(deploymentId)) return
    const next = new Set(deploymentsInProgress.value)
    next.delete(deploymentId)
    deploymentsInProgress.value = next
  }

  const $reset = () => {
    deploymentsInProgress.value = new Set()
  }

  return { deploymentsInProgress, isInProgress, start, end, $reset }
})
