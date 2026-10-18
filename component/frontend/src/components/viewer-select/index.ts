export { default as ViewerSelect } from './ViewerSelect.vue'
export { default as ViewerSelectDropdownItem } from './ViewerSelectDropdownItem.vue'

export interface Viewer {
  id: string
  loading: boolean
  // Why the viewer is not usable yet, or a caveat when it is (e.g. the RDP
  // step the desktop is in). Shown as the button tooltip and, on touch, as a
  // toast when the button is tapped, so the card never grows to show it.
  status?: string
  // 'warn' may be opened with a caveat (RDP unverifiable), 'error' the guest refused.
  tone?: 'wait' | 'warn' | 'error' | 'info'
  // 0-100 while a step is shown, so the button fills left to right; absent when ready.
  progress?: number
  // TODO: should you pass loading for each viewer, or should the component manage it based on a global loading prop?
}
