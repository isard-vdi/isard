import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

export type OwnershipTab = 'user' | 'shared'

interface UseOwnershipTabOptions {
  hasOwned: () => Promise<boolean>
  // Only asked when nothing is owned.
  hasShared: () => Promise<boolean>
  pinned?: OwnershipTab
  fallback?: () => OwnershipTab
  // `false` for a component that has no business touching the URL.
  param?: string | false
}

const parseTab = (value: unknown): OwnershipTab | undefined =>
  value === 'user' || value === 'shared' ? value : undefined

export function useOwnershipTab({
  hasOwned,
  hasShared,
  pinned,
  fallback = () => 'user',
  param = 'tab'
}: UseOwnershipTabOptions) {
  const route = useRoute()
  const router = useRouter()

  const settled = pinned ?? (param === false ? undefined : parseTab(route.query[param]))
  const tab = ref<OwnershipTab | undefined>(settled)
  const isResolving = ref(settled === undefined)

  // Whoever decides first wins, so a click mid-flight beats the autoselection.
  const autoselect = (value: OwnershipTab) => {
    if (tab.value === undefined) tab.value = value
  }

  if (isResolving.value) {
    void (async () => {
      try {
        if (!(await hasOwned()) && (await hasShared())) {
          autoselect('shared')
        }
      } catch {
        // A failed check falls through to the fallback.
      } finally {
        autoselect(fallback())
        isResolving.value = false
      }
    })()
  }

  // Only a deliberate change goes through the setter, so the autoselection stays
  // a per-visit decision while a hand-picked tab survives a reload or a back.
  const activeTab = computed<OwnershipTab | undefined>({
    get: () => tab.value,
    set: (value) => {
      if (value === undefined) return
      tab.value = value
      isResolving.value = false
      if (param !== false && route.query[param] !== value) {
        void router.replace({ query: { ...route.query, [param]: value } })
      }
    }
  })

  return { activeTab, isResolving }
}
