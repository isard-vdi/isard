import desktopsEmptyImg from '@/assets/img/desktops-empty.svg'
import templatesEmptyImg from '@/assets/img/templates-empty.svg'

// Two illustrations cover every resource for now; copy lives under
// `components.empty.<kind>`. Swap an entry when design delivers a bespoke one.
export const EMPTY_STATE_IMAGES = {
  desktops: desktopsEmptyImg,
  deployments: desktopsEmptyImg,
  'shared-deployments': desktopsEmptyImg,
  'deployment-users': desktopsEmptyImg,
  templates: templatesEmptyImg,
  'shared-templates': templatesEmptyImg,
  media: templatesEmptyImg,
  'shared-media': templatesEmptyImg,
  'recycle-bin': templatesEmptyImg
} as const

export type EmptyStateKind = keyof typeof EMPTY_STATE_IMAGES
