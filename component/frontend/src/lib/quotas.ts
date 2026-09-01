import type { QueryClient } from '@tanstack/vue-query'
import {
  checkQuotaNewDesktopOptions,
  checkQuotaNewVolatileDesktopOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { QUOTA_STALE_TIME } from '@/lib/constants'

// Temporal desktops count against the volatile quota, so a full desktops quota
// alone must not block the new-desktop flow.
export const canCreateAnyDesktop = async (
  queryClient: QueryClient,
  temporalAvailable: boolean
): Promise<boolean> => {
  try {
    await queryClient.fetchQuery({
      ...checkQuotaNewDesktopOptions(),
      staleTime: QUOTA_STALE_TIME
    })
    return true
  } catch {
    if (!temporalAvailable) return false
  }
  try {
    await queryClient.fetchQuery({
      ...checkQuotaNewVolatileDesktopOptions(),
      staleTime: QUOTA_STALE_TIME
    })
    return true
  } catch {
    return false
  }
}
