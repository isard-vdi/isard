export const VUE2_TO_VUE3 = {
  desktops: '/frontend/desktops',
  templates: '/frontend/templates',
  deployments: '/frontend/deployments',
  deployment_desktops: '/frontend/deployments/:id',
  media: '/frontend/media',
  recycleBins: '/frontend/recycle-bin',
  recycleBin: '/frontend/recycle-bin/:id',
  profile: '/frontend/profile'
}

export const EDIT_FORM_ROUTES = new Set([
  'desktopsnew',
  'templatenew',
  'templateduplicate',
  'deploymentsnew',
  'deploymentEdit',
  'medianew',
  'newfrommedia',
  'domainedit'
])

export function resolveVue3Path (route) {
  if (!route || !route.name) return null
  const template = VUE2_TO_VUE3[route.name]
  if (!template) return null
  return template.replace(/:([a-zA-Z]+)/g, (_, param) => {
    const value = route.params && route.params[param]
    return typeof value === 'string' ? value : ''
  })
}
