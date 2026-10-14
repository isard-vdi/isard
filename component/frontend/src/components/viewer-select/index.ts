export { default as ViewerSelect } from './ViewerSelect.vue'
export { default as ViewerSelectDropdownItem } from './ViewerSelectDropdownItem.vue'

export interface Viewer {
  id: string
  loading: boolean
  // Why the viewer is not usable yet, or a caveat when it is (e.g. the RDP
  // step the desktop is in). Shown as the button tooltip and, on touch, as a
  // toast when the button is tapped, so the card never grows to show it.
  status?: string
  // 'error' marks a viewer the guest refused: the button shows a warning icon
  tone?: 'wait' | 'error' | 'info'
  // TODO: should you pass loading for each viewer, or should the component manage it based on a global loading prop?
}
