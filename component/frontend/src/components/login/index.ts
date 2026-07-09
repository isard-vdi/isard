export { default as LoginProviderForm } from './LoginProviderForm.vue'
export { default as LoginProviderExternal } from './LoginProviderExternal.vue'
export { default as LoginCategoriesDropdown } from './LoginCategoriesDropdown.vue'
export { default as LoginCategorySelect } from './LoginCategorySelect.vue'
export { default as LoginNotification } from './LoginNotification.vue'

export { Provider, isProvider } from '@/lib/auth'

export type CategorySelectToken = {
  id: string
  name: string
  photo: string
}[]
