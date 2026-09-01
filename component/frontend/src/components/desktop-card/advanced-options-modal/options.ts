import type { Component } from 'vue'

import { NOT_USER_ROLES, type Role } from '@/lib/auth'

import StorageOptionsPanel from './StorageOptionsPanel.vue'

export interface AdvancedOption {
  id: string
  labelKey: string
  descriptionKey: string
  icon: string
  component: Component
  roles: readonly Role[]
}

export const ADVANCED_OPTIONS: AdvancedOption[] = [
  {
    id: 'storage',
    labelKey: 'components.desktops.advanced-options-modal.options.storage.label',
    descriptionKey: 'components.desktops.advanced-options-modal.options.storage.description',
    icon: 'hard-drive',
    component: StorageOptionsPanel,
    // The API gates the resize endpoints with `@is_not_user`.
    roles: NOT_USER_ROLES
  }
]

export const advancedOptionsForRole = (role: string | undefined): AdvancedOption[] =>
  ADVANCED_OPTIONS.filter((option) => option.roles.includes((role ?? 'user') as Role))

/** Whether the entry point should be offered at all to this role. */
export const hasAdvancedOptions = (role: string | undefined): boolean =>
  advancedOptionsForRole(role).length > 0
