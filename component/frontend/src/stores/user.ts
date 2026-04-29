import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getUserConfig as fetchUserConfig } from '@/gen/oas/apiv4'

export const useUserStore = defineStore('user', () => {
  const config = ref<Record<string, unknown> | null>(null)

  const getUserConfig = async (): Promise<void> => {
    try {
      const response = await fetchUserConfig()
      if (response.error) {
        throw new Error('Failed to fetch user config')
      }
      config.value = response.data
    } catch (error) {
      console.error('Error fetching user config:', error)
      throw error
    }
  }

  const $reset = () => {
    config.value = null
  }

  return {
    config,
    $reset,
    getUserConfig
  }
})
