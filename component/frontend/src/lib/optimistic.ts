import type { QueryClient, QueryKey, UseMutationOptions } from '@tanstack/vue-query'

/**
 * Wraps a generated TanStack mutation with an optimistic write so the user
 * sees a transitional state immediately on click, instead of waiting for the
 * apiv4 → engine → changefeed → WebSocket round-trip.
 *
 * Behaviour:
 *   - onMutate: snapshot the current cache, then patch the targeted item to
 *     the supplied transitional status (Start → Starting, Stop → Stopping,…).
 *   - onError: roll back to the snapshot if the mutation failed.
 *   - onSettled: nothing. The matching `*_update` WebSocket event delivered
 *     by the change-handler carries the new server-side status and patches
 *     the cache via `stores/ws-handlers/*`. No client-driven refetch — that
 *     would race the engine's status write.
 *
 * Caller hooks (`onError`, `onSuccess`) run after the helper's bookkeeping.
 */

type ListEnvelope<TItem, K extends string> = { [P in K]: TItem[] } & Record<string, unknown>

interface BaseOpts<TVars> {
  queryClient: QueryClient
  queryKey: QueryKey
  extractItemId: (vars: TVars) => string
  baseMutation: UseMutationOptions<unknown, unknown, TVars, unknown>
  onError?: NonNullable<UseMutationOptions<unknown, unknown, TVars, unknown>['onError']>
  onSuccess?: NonNullable<UseMutationOptions<unknown, unknown, TVars, unknown>['onSuccess']>
}

interface StatusFlipOpts<TVars, TItem, K extends string> extends BaseOpts<TVars> {
  /** Property name in the envelope that holds the item array, e.g. `'desktops'`. */
  listKey: K
  /** Field on each item that carries the status, default `'status'`. */
  statusKey?: keyof TItem & string
  /** Status to optimistically write to the targeted item. */
  nextStatus: TItem[keyof TItem]
  /**
   * Predicate over the targeted item's current status. When provided and it
   * returns `false`, `onMutate` skips the cache patch — guarding against
   * double-clicks during a flicker (e.g. firing `desktopStart` while the row
   * is already `Started`, which the engine would early-return on, leaving
   * the optimistic `Starting` write to fight the WS event).
   */
  nextStatusGuard?: (currentStatus: TItem[keyof TItem]) => boolean
}

/**
 * Optimistically flip a single item's status field in the cached list.
 */
export function withOptimisticItemStatus<TVars, TItem, K extends string>(
  opts: StatusFlipOpts<TVars, TItem, K>
): UseMutationOptions<unknown, unknown, TVars, unknown> {
  const statusKey = (opts.statusKey ?? 'status') as keyof TItem & string

  return {
    ...opts.baseMutation,
    onMutate: async (vars) => {
      const id = opts.extractItemId(vars)
      await opts.queryClient.cancelQueries({ queryKey: opts.queryKey })
      const prev = opts.queryClient.getQueryData(opts.queryKey)
      opts.queryClient.setQueryData(opts.queryKey, (old: ListEnvelope<TItem, K> | undefined) => {
        if (!old || !Array.isArray(old[opts.listKey])) return old
        const items = old[opts.listKey] as TItem[]
        if (opts.nextStatusGuard) {
          const target = items.find((item) => (item as unknown as { id: string }).id === id)
          if (target && !opts.nextStatusGuard(target[statusKey] as TItem[keyof TItem])) {
            return old
          }
        }
        return {
          ...old,
          [opts.listKey]: items.map((item) =>
            (item as unknown as { id: string }).id === id
              ? { ...item, [statusKey]: opts.nextStatus }
              : item
          )
        } as ListEnvelope<TItem, K>
      })
      return { prev }
    },
    onError: (err, vars, context) => {
      const ctx = context as { prev?: unknown } | undefined
      if (ctx?.prev !== undefined) {
        opts.queryClient.setQueryData(opts.queryKey, ctx.prev)
      }
      opts.onError?.(err, vars, context)
    },
    onSuccess: (data, vars, context) => {
      opts.onSuccess?.(data, vars, context)
    }
  }
}

interface RemovalOpts<TVars, TItem, K extends string> extends BaseOpts<TVars> {
  listKey: K
  matches?: (item: TItem, id: string) => boolean
}

/**
 * Optimistically drop an item from the cached list (delete flows).
 */
export function withOptimisticItemRemoval<TVars, TItem, K extends string>(
  opts: RemovalOpts<TVars, TItem, K>
): UseMutationOptions<unknown, unknown, TVars, unknown> {
  const matches =
    opts.matches ?? ((item: TItem, id: string) => (item as unknown as { id: string }).id === id)

  return {
    ...opts.baseMutation,
    onMutate: async (vars) => {
      const id = opts.extractItemId(vars)
      await opts.queryClient.cancelQueries({ queryKey: opts.queryKey })
      const prev = opts.queryClient.getQueryData(opts.queryKey)
      opts.queryClient.setQueryData(opts.queryKey, (old: ListEnvelope<TItem, K> | undefined) => {
        if (!old || !Array.isArray(old[opts.listKey])) return old
        return {
          ...old,
          [opts.listKey]: (old[opts.listKey] as TItem[]).filter((item) => !matches(item, id))
        } as ListEnvelope<TItem, K>
      })
      return { prev }
    },
    onError: (err, vars, context) => {
      const ctx = context as { prev?: unknown } | undefined
      if (ctx?.prev !== undefined) {
        opts.queryClient.setQueryData(opts.queryKey, ctx.prev)
      }
      opts.onError?.(err, vars, context)
    },
    onSuccess: (data, vars, context) => {
      opts.onSuccess?.(data, vars, context)
    }
  }
}
