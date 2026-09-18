export type DesktopKind = 'persistent' | 'nonpersistent' | 'deployment'
export type DomainKind = DesktopKind | 'template'

export interface DomainKindStyle {
  /** Left border of the card that frames the domain. */
  accent: string
  /** Name badge and section headers. */
  badge: string
  /** `stroke-color` token for the icons sitting on `badge`. */
  iconColor: string
  /** Soft fill behind inline values (ids, credentials, ip). */
  tint: string
  /** The icon the kind answers to, the one its cards carry. */
  icon: string
}

const DOMAIN_KIND_STYLES: Record<DomainKind, DomainKindStyle> = {
  persistent: {
    accent: 'border-l-6 border-l-secondary-3-500',
    badge: 'bg-secondary-3-300 text-secondary-3-600',
    iconColor: 'secondary-3-600',
    tint: 'bg-secondary-3-100',
    icon: 'browser'
  },
  nonpersistent: {
    accent: 'border-l-6 border-l-secondary-1-500',
    badge: 'bg-secondary-1-300 text-secondary-1-600',
    iconColor: 'secondary-1-600',
    tint: 'bg-secondary-1-100',
    icon: 'clock'
  },
  deployment: {
    accent: 'border-l-6 border-l-secondary-2-500',
    badge: 'bg-secondary-2-300 text-secondary-2-600',
    iconColor: 'secondary-2-600',
    tint: 'bg-secondary-2-100',
    icon: 'layout-alt-04'
  },
  // A gray deep enough to keep its distance from the persistent teal: the lighter
  // ones collapse onto it with red-green colour blindness.
  template: {
    accent: 'border-l-6 border-l-gray-warm-500',
    badge: 'bg-gray-warm-200 text-gray-warm-800',
    iconColor: 'gray-warm-700',
    tint: 'bg-gray-warm-100',
    icon: 'colors'
  }
}

export const domainKindStyle = (kind: DomainKind = 'template'): DomainKindStyle =>
  DOMAIN_KIND_STYLES[kind]

/** The accent a domain answers to: desktops by their own kind, the rest as templates. */
export const resolveDomainKind = (
  kind: 'desktop' | 'template',
  desktopKind?: DesktopKind | null
): DomainKind => (kind === 'desktop' && desktopKind ? desktopKind : 'template')
