import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import { i18n } from '@/lib/i18n'
import DataTable from './DataTable.vue'

// The real plugin: the nested pagination renders with the global `$t`, and
// `src/lib/utils` builds the i18n instance at import time anyway.
const global = { plugins: [i18n] }

const headers = [
  { name: 'User', key: 'name' },
  { name: 'Visible', key: 'visible' }
]
const rows = [{ name: 'alice', visible: true }]

describe('DataTable header slot', () => {
  it('falls back to the header name when no head slot is given', () => {
    // Guards the ~10 existing consumers, none of which pass a head slot.
    const wrapper = mount(DataTable, {
      props: { headers, rows, isClickable: false, cellClass: '' },
      global
    })
    expect(wrapper.text()).toContain('User')
    expect(wrapper.text()).toContain('Visible')
  })

  it('renders a head slot in place of the plain name', () => {
    const wrapper = mount(DataTable, {
      props: { headers, rows, isClickable: false, cellClass: '' },
      global,
      slots: { 'head-visible': '<span data-test="custom">custom head</span>' }
    })
    expect(wrapper.find('[data-test="custom"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('User') // the other column is untouched
  })

  it('passes the header to the head slot', () => {
    const wrapper = mount(DataTable, {
      props: { headers, rows, isClickable: false, cellClass: '' },
      global,
      slots: { 'head-visible': '<template #default="{ header }">{{ header.key }}</template>' }
    })
    expect(wrapper.text()).toContain('visible')
  })

  it('applies a per-column cellClass to the body cells', () => {
    const wrapper = mount(DataTable, {
      props: {
        headers: [{ name: 'User', key: 'name', cellClass: 'justify-center' }],
        rows,
        isClickable: false,
        cellClass: 'h-19'
      },
      global
    })
    const cell = wrapper
      .findAll('div')
      .find((node) => node.text() === 'alice' && node.classes().includes('p-2'))
    expect(cell?.classes()).toContain('justify-center')
    expect(cell?.classes()).toContain('h-19')
  })

  it('pins a sticky column against the horizontal scroll', () => {
    const wrapper = mount(DataTable, {
      props: {
        headers: [{ name: 'User', key: 'name', sticky: 'left' as const }],
        rows,
        isClickable: false,
        cellClass: ''
      },
      global
    })
    expect(wrapper.html()).toContain('sticky')
    expect(wrapper.html()).toContain('left-0')
  })
})
