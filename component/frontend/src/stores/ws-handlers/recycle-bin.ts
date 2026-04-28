import { QueryClient } from '@tanstack/vue-query'
import {
  getRecycleBinItemCountUserOptions,
  getUserOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { RecycleBinStatusEnum } from '@/gen/oas/apiv4'
import { patchEntityList } from '@/lib/utils'

const listKey = getRecycleBinItemCountUserOptions().queryKey
const userKey = getUserOptions().queryKey

const removableStatuses = new Set<RecycleBinStatusEnum>([
  RecycleBinStatusEnum.RESTORED,
  RecycleBinStatusEnum.DELETING,
  RecycleBinStatusEnum.DELETED
])

const shouldRemoveEntry = (status?: RecycleBinStatusEnum) =>
  status ? removableStatuses.has(status) : false

function syncItemsInBin(queryClient: QueryClient, entriesCount: number) {
  queryClient.setQueryData(userKey, (old: any) => {
    if (!old) return old
    return {
      ...old,
      items_in_bin: Math.max(0, entriesCount)
    }
  })
}

export const recycleBinEventHandlers = {
  add_recycle_bin: (queryClient: QueryClient, payload: any) => {
    const data = JSON.parse(payload)
    queryClient.setQueryData(listKey, (old: any = {}) => {
      const entries = patchEntityList(
        old.entries || [],
        old.entries?.some((item: any) => item.id === data.id) ? 'update' : 'add',
        data
      )
      syncItemsInBin(queryClient, data?.items_in_bin ?? entries.length)
      return { ...old, entries }
    })
  },
  update_recycle_bin: (queryClient: QueryClient, payload: any) => {
    const data = JSON.parse(payload)
    const action = shouldRemoveEntry(data?.status) ? 'delete' : 'update'
    queryClient.setQueryData(listKey, (old: any = {}) => {
      const entries = patchEntityList(old.entries || [], action, data)
      syncItemsInBin(queryClient, entries.length)
      return { ...old, entries }
    })
  },
  delete_recycle_bin: (queryClient: QueryClient, payload: any) => {
    const data = JSON.parse(payload)
    queryClient.setQueryData(listKey, (old: any = {}) => {
      const entries = patchEntityList(old.entries || [], 'delete', data)
      syncItemsInBin(queryClient, entries.length)
      return { ...old, entries }
    })
  }
}
