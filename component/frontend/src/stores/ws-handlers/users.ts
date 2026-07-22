import { QueryClient } from '@tanstack/vue-query'
import { getUserOptions, getUserDetailsOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

const userKey = getUserOptions().queryKey
const userDetailsKey = getUserDetailsOptions().queryKey

export const usersEventHandlers = {
  users_data: (queryClient: QueryClient, _payload: string) => {
    queryClient.invalidateQueries({ queryKey: userKey })
    queryClient.invalidateQueries({ queryKey: userDetailsKey })
  },
  users_delete: (queryClient: QueryClient, _payload: string) => {
    queryClient.invalidateQueries({ queryKey: userKey })
    queryClient.invalidateQueries({ queryKey: userDetailsKey })
  }
}
