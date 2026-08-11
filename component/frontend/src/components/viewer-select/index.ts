export { default as ViewerSelect } from './ViewerSelect.vue'
export { default as ViewerSelectDropdownItem } from './ViewerSelectDropdownItem.vue'

export interface Viewer {
  id: string
  loading: boolean
  // TODO: should you pass loading for each viewer, or should the component manage it based on a global loading prop?
}
