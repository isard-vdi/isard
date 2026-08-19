import { toValue, type MaybeRefOrGetter } from 'vue'
import { onKeyStroke } from '@vueuse/core'

// Keyboard shortcuts for a list view's search box, addressed by element id so
// it works with any input that renders one.
export function useSearchShortcuts(inputId: MaybeRefOrGetter<string>) {
  const getSearchInput = () => document.getElementById(toValue(inputId))

  const focusSearch = () => {
    getSearchInput()?.focus()
  }

  // `/` jumps to the search box, unless the user is already typing somewhere
  onKeyStroke('/', (event) => {
    if (event.ctrlKey || event.metaKey || event.altKey) {
      return
    }

    const target = event.target as HTMLElement | null
    if (
      target?.isContentEditable ||
      ['INPUT', 'TEXTAREA', 'SELECT'].includes(target?.tagName ?? '')
    ) {
      return
    }

    event.preventDefault()
    focusSearch()
  })

  // ctrl/cmd + k is what most people reach for, so it works from anywhere
  onKeyStroke('k', (event) => {
    if (!event.ctrlKey && !event.metaKey) {
      return
    }

    event.preventDefault()
    focusSearch()
  })

  // Esc leaves the search box, without touching the Esc handling of any open modal
  onKeyStroke('Escape', () => {
    const searchInput = getSearchInput()
    if (searchInput && document.activeElement === searchInput) {
      searchInput.blur()
    }
  })

  return { focusSearch }
}
