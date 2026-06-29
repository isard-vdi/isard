import type { RouteLocationNormalized } from 'vue-router'

export type FrontendMode = 'deprecated' | 'actual' | 'all' | 'hidden'

export const VUE3_TO_VUE2: Record<string, string> = {
  desktops: '/desktops',
  'single-desktop': '/desktops',
  templates: '/templates',
  deployments: '/deployments',
  deployment: '/deployment/:deploymentId',
  media: '/media',
  'recycle-bin': '/recycleBins',
  'recycle-bin-entry': '/recyclebin/:recycleBinId',
  profile: '/profile'
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
