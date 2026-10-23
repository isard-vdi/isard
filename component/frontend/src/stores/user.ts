import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import type { UserConfigResponse } from '@/gen/oas/apiv4'
import {
  getUserConfigOptions,
  getUserConfigQueryKey
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

export const useUserStore = defineStore('user', () => {
  const queryClient = useQueryClient()
  const config = ref<Record<string, unknown> | null>(null)

  const getUserConfig = async ({ refresh = false } = {}): Promise<UserConfigResponse> => {
    try {
      const options = getUserConfigOptions()
      const data = refresh
        ? await queryClient.fetchQuery({ ...options, staleTime: 0 })
        : await queryClient.ensureQueryData(options)
      config.value = data
      return data
    } catch (error) {
      console.error('Error fetching user config:', error)
      throw error
    }
  }

  const $reset = () => {
    config.value = null
    queryClient.removeQueries({ queryKey: getUserConfigQueryKey() })
  }

  return {
    config,
    $reset,
    getUserConfig
  }
})
