import { QueryClient } from '@tanstack/vue-query'
import {
  getUserApiV4ItemUserGetOptions,
  getUserDetailsApiV4ItemUserGetDetailsGetOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

const userKey = getUserApiV4ItemUserGetOptions().queryKey
const userDetailsKey = getUserDetailsApiV4ItemUserGetDetailsGetOptions().queryKey

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
