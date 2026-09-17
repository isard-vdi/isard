export { default as FilterTags } from './FilterTags.vue'
export type { FilterCategory, FilterOption } from './FilterTags.vue'

export type FilterTagsSelection = Record<string, string[]>

export const emptyFilterTags = (categoryKeys: string[]): FilterTagsSelection =>
  Object.fromEntries(categoryKeys.map((key) => [key, []]))

export const countFilterTags = (selection: FilterTagsSelection): number =>
  Object.values(selection).reduce((total, values) => total + values.length, 0)
