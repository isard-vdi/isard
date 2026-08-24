import { ref, toValue, type MaybeRefOrGetter } from 'vue'
import { onBeforeRouteLeave, useRouter, type RouteLocationRaw } from 'vue-router'
import { useEventListener } from '@vueuse/core'

/**
 * Confirms leaving a form with unsaved changes, whatever the exit route is:
 * the form's own cancel button, a sidebar link, the browser back button or a
 * page reload.
 *
 * @param hasUnsavedChanges - Whether the form holds edits worth confirming.
 */
export function useUnsavedChangesGuard(hasUnsavedChanges: MaybeRefOrGetter<boolean>) {
  const router = useRouter()

  const showDiscardModal = ref(false)
  const pendingTarget = ref<RouteLocationRaw | null>(null)
  // Plain flag: the route guard reads it synchronously, so a prop would race with rendering
  let leaveAllowed = false

  /** Leave without asking, e.g. once the form has been submitted. */
  const allowLeave = () => {
    leaveAllowed = true
  }

  const shouldConfirm = () => !leaveAllowed && toValue(hasUnsavedChanges)

  onBeforeRouteLeave((to) => {
    if (!shouldConfirm()) return true
    pendingTarget.value = to.fullPath
    showDiscardModal.value = true
    return false
  })

  useEventListener(window, 'beforeunload', (event: BeforeUnloadEvent) => {
    if (!shouldConfirm()) return
    event.preventDefault()
    event.returnValue = ''
  })

  const confirmDiscard = () => {
    showDiscardModal.value = false
    const target = pendingTarget.value
    pendingTarget.value = null
    if (!target) return
    allowLeave()
    // Re-arm the guard if the navigation never happened (redirected, aborted...)
    void router.push(target).finally(() => {
      leaveAllowed = false
    })
  }

  const cancelDiscard = () => {
    showDiscardModal.value = false
    pendingTarget.value = null
  }

  /** Navigate away, asking for confirmation first when there are unsaved changes. */
  const requestLeave = (target: RouteLocationRaw) => {
    pendingTarget.value = target
    if (shouldConfirm()) {
      showDiscardModal.value = true
      return
    }
    confirmDiscard()
  }

  return { showDiscardModal, requestLeave, confirmDiscard, cancelDiscard, allowLeave }
}
