import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      params && Object.keys(params).length ? `${key}::${JSON.stringify(params)}` : key
  }),
  // @/lib/utils pulls in @/lib/i18n, which calls createI18n at module load.
  createI18n: () => ({ global: { locale: { value: 'en-US' }, t: (key: string) => key } })
}))

import FilterTags from './FilterTags.vue'
import type { FilterCategory } from './FilterTags.vue'

const categories: FilterCategory[] = [
  {
    key: 'kind',
    label: 'Type',
    options: [
      { value: 'persistent', label: 'Persistents', count: 12 },
      { value: 'volatile', label: 'Temporaries', count: 3 }
    ]
  },
  {
    key: 'status',
    label: 'Status',
    options: [{ value: 'started', label: 'Started', count: 4 }]
  }
]

const mountTags = (modelValue: Record<string, string[]>) =>
  mount(FilterTags, { props: { categories, modelValue }, attachTo: document.body })

const tagsOf = (wrapper: ReturnType<typeof mountTags>) =>
  wrapper.findAll('button[aria-label^="components.filters.remove"]')

describe('FilterTags', () => {
  it('renders a tag per selected value, across categories', () => {
    const wrapper = mountTags({ kind: ['persistent'], status: ['started'] })
    expect(wrapper.text()).toContain('Persistents')
    expect(wrapper.text()).toContain('Started')
    expect(tagsOf(wrapper)).toHaveLength(2)
  })

  it('drops only the removed value from its own category', async () => {
    const wrapper = mountTags({ kind: ['persistent', 'volatile'], status: ['started'] })
    await tagsOf(wrapper)[0].trigger('click')

    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual({
      kind: ['volatile'],
      status: ['started']
    })
  })

  it('shows the placeholder and no tags when nothing is selected', () => {
    const wrapper = mountTags({ kind: [], status: [] })
    expect(tagsOf(wrapper)).toHaveLength(0)
    expect(wrapper.text()).toContain('components.filters.toggle')
  })

  it('counts every selected value in the trigger label', () => {
    const wrapper = mountTags({ kind: ['persistent'], status: ['started'] })
    expect(wrapper.find('[aria-haspopup="menu"]').attributes('aria-label')).toBe(
      'components.filters.toggle-active::{"count":2}'
    )
  })
})
