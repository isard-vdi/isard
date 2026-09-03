import { ref, watch } from 'vue'
import { useCookies } from '@vueuse/integrations/useCookies'

const FILTER_PANEL_COOKIE_MAX_AGE = 60 * 60 * 24 * 7

// Keeps a view's filter panel expanded across navigations and reloads.
export function useFilterPanel(cookieName: string) {
  const cookies = useCookies([cookieName])

  // useCookies auto-parses "true"/"false" to boolean, so check both types
  const stored = cookies.get(cookieName)
  const open = ref(stored === true || stored === 'true')

  watch(open, (value) => {
    cookies.set(cookieName, String(value), {
      path: '/',
      maxAge: FILTER_PANEL_COOKIE_MAX_AGE
    })
  })

  return open
}
