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
      { value: 'persistent', label: 'Persistents', count: 12, tone: 'persistent', icon: 'browser' },
      { value: 'volatile', label: 'Temporaries', count: 3, tone: 'nonpersistent', icon: 'clock' }
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

  it('fills a kind tag with the colour its value answers to, and leaves the rest neutral', () => {
    const wrapper = mountTags({ kind: ['persistent'], status: ['started'] })
    const [kindTag, statusTag] = wrapper.findAll('span.inline-flex.h-7')

    expect(kindTag.classes()).toContain('bg-secondary-3-300')
    expect(kindTag.classes()).toContain('text-secondary-3-600')
    expect(statusTag.classes()).toContain('bg-gray-warm-100')
  })

  it('carries the count of what the filter leaves behind', () => {
    const wrapper = mountTags({ kind: ['persistent'], status: [] })
    expect(wrapper.findAll('span.inline-flex.h-7')[0].text()).toContain('12')
  })

  it('lifts every filter at once from the row, without opening the menu', async () => {
    const wrapper = mountTags({ kind: ['persistent', 'volatile'], status: ['started'] })
    await wrapper.find('[data-filter-actions] button:last-child').trigger('click')

    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual({ kind: [], status: [] })
  })

  it('offers nothing to clear while no filter is on', () => {
    const wrapper = mountTags({ kind: [], status: [] })
    expect(wrapper.find('[data-filter-actions] button').exists()).toBe(false)
  })

  it('counts every selected value in the trigger label', () => {
    const wrapper = mountTags({ kind: ['persistent'], status: ['started'] })
    expect(wrapper.find('[aria-haspopup="menu"]').attributes('aria-label')).toBe(
      'components.filters.toggle-active::{"count":2}'
    )
  })
})
