import { domainKindStyle, type DomainKind } from '@/lib/domainKind'

export { default as FilterTags } from './FilterTags.vue'
export type { FilterCategory, FilterOption } from './FilterTags.vue'

export type FilterTagsSelection = Record<string, string[]>

export const emptyFilterTags = (categoryKeys: string[]): FilterTagsSelection =>
  Object.fromEntries(categoryKeys.map((key) => [key, []]))

export const countFilterTags = (selection: FilterTagsSelection): number =>
  Object.values(selection).reduce((total, values) => total + values.length, 0)

export type FilterTone = DomainKind | 'neutral'

export interface FilterToneStyle {
  /** The tag's fill and the text that stays readable on it. */
  fill: string
  /** Fill behind the count, a step away from the tag's own. */
  count: string
  /** `stroke-color` token for the icon. In the menu, where nothing is filled,
   *  this is the whole of the colour a value carries. */
  iconColor: string
}

const LIGHT_KIND_ICONS: Record<DomainKind, string> = {
  persistent: 'secondary-3-550',
  nonpersistent: 'secondary-1-550',
  deployment: 'secondary-2-550',
  template: 'gray-warm-600'
}

const FILTER_TONE_STYLES: Record<FilterTone, FilterToneStyle> = {
  persistent: {
    fill: domainKindStyle('persistent').badge,
    count: 'bg-base-white/60',
    iconColor: LIGHT_KIND_ICONS.persistent
  },
  nonpersistent: {
    fill: domainKindStyle('nonpersistent').badge,
    count: 'bg-base-white/60',
    iconColor: LIGHT_KIND_ICONS.nonpersistent
  },
  deployment: {
    fill: domainKindStyle('deployment').badge,
    count: 'bg-base-white/60',
    iconColor: LIGHT_KIND_ICONS.deployment
  },
  template: {
    fill: domainKindStyle('template').badge,
    count: 'bg-base-white/60',
    iconColor: LIGHT_KIND_ICONS.template
  },
  // Started, stopped, visible, hidden: the icon tells them apart, so the fill
  // stays out of the way and lets the coloured kinds be the ones that carry.
  neutral: {
    fill: 'bg-gray-warm-100 text-gray-warm-800',
    count: 'bg-gray-warm-200',
    iconColor: 'gray-warm-700'
  }
}

export const filterToneStyle = (tone: FilterTone = 'neutral'): FilterToneStyle =>
  FILTER_TONE_STYLES[tone] ?? FILTER_TONE_STYLES.neutral
