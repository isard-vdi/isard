import type { Directive } from 'vue'

type FocusableField = HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | HTMLButtonElement

const FIELD_SELECTOR = 'input:not([type="hidden"]), textarea, select, button'

interface AutofocusState {
  frame?: number
  done: boolean
  /** Focus when the field could not take it yet; a later retry only fires while it is unchanged. */
  activeWhenDeferred?: Element | null
}

const states = new WeakMap<HTMLElement, AutofocusState>()

// The directive can sit on the field itself or on a component wrapping it.
function findField(el: HTMLElement): FocusableField | null {
  return el.matches(FIELD_SELECTOR) ? (el as FocusableField) : el.querySelector(FIELD_SELECTOR)
}

function focusField(el: HTMLElement): boolean {
  const field = findField(el)
  if (!field || field.disabled || !field.isConnected) return false
  field.focus({ preventScroll: true })
  // A hidden field (`v-show`, a closed step) silently refuses focus.
  if (document.activeElement !== field) return false
  const rect = field.getBoundingClientRect()
  if (rect.top < 0 || rect.bottom > window.innerHeight) {
    field.scrollIntoView({ block: 'nearest' })
  }
  return true
}

function attempt(el: HTMLElement, state: AutofocusState) {
  if (state.frame !== undefined) cancelAnimationFrame(state.frame)
  // One frame later: a reka-ui dialog's FocusScope has already run its own mount
  // autofocus by then, so it still restores focus to the trigger on close.
  state.frame = requestAnimationFrame(() => {
    state.frame = undefined
    if (state.done) return
    const deferred = state.activeWhenDeferred !== undefined
    if (
      deferred &&
      document.activeElement !== state.activeWhenDeferred &&
      document.activeElement !== document.body
    ) {
      state.done = true
      return
    }
    state.done = focusField(el)
    if (!state.done && !deferred) state.activeWhenDeferred = document.activeElement
  })
}

/**
 * Focuses the element, or the first form field inside it, once it is mounted and
 * usable. `v-autofocus="false"` opts out. A disabled or hidden field is retried
 * on each update until it can take the focus.
 */
export const vAutofocus: Directive<HTMLElement, boolean | undefined> = {
  mounted(el, { value }) {
    const state: AutofocusState = { done: value === false }
    states.set(el, state)
    if (!state.done) attempt(el, state)
  },
  updated(el, { value, oldValue }) {
    const state = states.get(el)
    if (!state || value === false) return
    if (oldValue === false) {
      state.done = false
      state.activeWhenDeferred = undefined
    }
    if (!state.done) attempt(el, state)
  },
  beforeUnmount(el) {
    const state = states.get(el)
    if (state?.frame !== undefined) cancelAnimationFrame(state.frame)
    states.delete(el)
  }
}
