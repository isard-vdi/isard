import type { RouteLocationNormalized } from 'vue-router'

export type FrontendMode = 'deprecated' | 'actual' | 'all' | 'hidden'

export type PreferredFrontend = 'vue2' | 'vue3'

// Same origin, so also read by the old frontend and by the webapp sidebar.
const PREFERRED_FRONTEND_KEY = 'preferredFrontend'

export function getPreferredFrontend(): PreferredFrontend | null {
  const stored = localStorage.getItem(PREFERRED_FRONTEND_KEY)
  return stored === 'vue2' || stored === 'vue3' ? stored : null
}

export function setPreferredFrontend(value: PreferredFrontend): void {
  localStorage.setItem(PREFERRED_FRONTEND_KEY, value)
}

export function clearPreferredFrontend(): void {
  localStorage.removeItem(PREFERRED_FRONTEND_KEY)
}

export const VUE3_TO_VUE2: Record<string, string> = {
  desktops: '/desktops',
  'single-desktop': '/desktops',
  templates: '/templates',
  deployments: '/deployments',
  'shared-deployments': '/deployments',
  deployment: '/deployment/:deploymentId',
  media: '/media',
  'recycle-bin': '/recycleBins',
  'recycle-bin-entry': '/recyclebin/:recycleBinId',
  profile: '/profile'
}

export function hasVue2Equivalent(name: string | undefined): boolean {
  return name != null && name in VUE3_TO_VUE2
}

export const EDIT_FORM_ROUTES = new Set<string>([
  'new-desktop',
  'edit-desktop',
  'new-template',
  'edit-template',
  'duplicate-template',
  'duplicate-template-root',
  'new-deployment'
])

export function resolveVue2Path(route: RouteLocationNormalized): string | null {
  const name = route.name as string | undefined
  if (!name) return null
  const template = VUE3_TO_VUE2[name]
  if (!template) return null
  return template.replace(/:([a-zA-Z]+)/g, (_, param) => {
    const value = route.params[param]
    return typeof value === 'string' ? value : ''
  })
}

export function vue2PathForRouteName(name: string | undefined): string | null {
  if (!name) return null
  const template = VUE3_TO_VUE2[name]
  if (!template || template.includes(':')) return null
  return template
}
