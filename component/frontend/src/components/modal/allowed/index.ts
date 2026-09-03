export { default as AllowedModal } from './AllowedModal.vue'
export { default as AllowedModalColumn } from './AllowedModalColumn.vue'
export { default as AllowedModalItem } from './AllowedModalItem.vue'

export interface AllowedOption {
  value: string
  label: string
  subLabel?: string | undefined
  avatar?: string | undefined
  icon?: string | undefined
}

export interface AllowedSelection {
  groups: boolean | string[]
  users: boolean | string[]
}
