export { default as LoginProviderForm } from './LoginProviderForm.vue'
export { default as LoginProviderExternal } from './LoginProviderExternal.vue'
export { default as LoginCategoriesDropdown } from './LoginCategoriesDropdown.vue'
export { default as LoginCategorySelect } from './LoginCategorySelect.vue'

// TODO: Move this to the correspondant place
export enum Provider {
  Form = 'form',
  SAML = 'saml',
  Google = 'google'
}

export type CategorySelectToken = Array<{
  id: string
  name: string
  photo: string
}>
