import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import { ref } from 'vue'
import { Button } from '@/components/ui/button'
import { AllowedModalColumn, type AllowedOption } from '.'

const groups: AllowedOption[] = Array.from({ length: 40 }, (_, index) => ({
  value: `group-${index}`,
  label: `Group ${index + 1}`,
  subLabel: index % 3 === 0 ? `Description for group ${index + 1}` : undefined,
  icon: 'users-01'
}))

const meta = {
  component: AllowedModalColumn,
  title: 'Modal/AllowedModalColumn',
  tags: ['autodocs'],
  parameters: {
    backgrounds: {
      default: 'base-background',
      values: [{ name: 'base-background', value: '#fbf8ee' }]
    }
  },
  argTypes: {
    title: { control: 'text', description: 'Heading above the search input.' },
    items: { control: 'object', description: 'Rows to list, before filtering.' },
    selected: { control: 'object', description: 'Values rendered as fully checked.' },
    indeterminate: {
      control: 'object',
      description: 'Values rendered with the indeterminate dash.'
    },
    activeId: { control: 'text', description: 'Value of the highlighted row, if any.' },
    loading: { control: 'boolean', description: 'Replaces the list with skeletons.' },
    disabled: { control: 'boolean', description: 'Dims the column and blocks every control.' },
    searchPlaceholder: { control: 'text', description: 'Placeholder of the search input.' },
    emptyText: { control: 'text', description: 'Shown when there is nothing to list at all.' },
    notFoundText: { control: 'text', description: 'Shown when the search matched nothing.' },
    footerText: {
      control: 'text',
      description:
        'Note appended as the last row of the list, so it scrolls with the items and only ' +
        'ever shows beneath results. Used for the "results were truncated" warning.'
    },
    selectAll: {
      control: 'boolean',
      description: 'Renders a tri-state row on top of the list that selects or clears every item.'
    },
    selectAllLabel: { control: 'text', description: 'Visible label of the select-all row.' },
    selectAllCountLabel: {
      control: 'text',
      description: 'Muted count shown at the end of the select-all row.'
    },
    selectAllChecked: {
      control: 'boolean',
      description:
        'Renders the row checked — the caller\'s "everyone" sentinel. Every row merely being ' +
        'ticked is a different state and reads as indeterminate.'
    }
  },
  render: (args) => ({
    components: { AllowedModalColumn },
    setup() {
      const search = ref('')
      const selected = ref<string[]>([...(args.selected ?? [])])
      const activeId = ref<string | null>(args.activeId ?? null)
      const toggle = (value: string) => {
        selected.value = selected.value.includes(value)
          ? selected.value.filter((id) => id !== value)
          : [...selected.value, value]
      }
      const selectAllChecked = ref(args.selectAllChecked ?? false)
      const toggleAll = (selectAll: boolean) => {
        selectAllChecked.value = selectAll
        selected.value = selectAll ? args.items.map((item) => item.value) : []
      }
      return { args, search, selected, activeId, selectAllChecked, toggle, toggleAll }
    },
    // The column only sizes itself correctly inside a parent with a definite height.
    // Only the checkboxes select; clicking a row is a separate event.
    template: `
      <div class="flex h-[420px] w-96 gap-6">
        <AllowedModalColumn
          v-bind="args"
          v-model:search="search"
          :selected="selected"
          :active-id="activeId"
          :select-all-checked="selectAllChecked"
          @toggle="toggle"
          @toggle-all="toggleAll"
          @select="activeId = $event"
        />
      </div>
    `
  })
} satisfies Meta<ComponentPropsAndSlots<typeof AllowedModalColumn>>

export default meta
type Story = StoryObj<ComponentPropsAndSlots<typeof AllowedModalColumn>>

const baseArgs = {
  title: 'Groups',
  items: groups,
  selected: [],
  searchPlaceholder: 'Search group',
  emptyText: 'No groups available',
  notFoundText: 'No group found'
}

/** 40 rows: the list scrolls inside the column, the search input stays put. */
export const Scrolling: Story = {
  args: baseArgs
}

export const WithSelection: Story = {
  args: {
    ...baseArgs,
    selected: ['group-1', 'group-4'],
    indeterminate: ['group-2', 'group-7'],
    activeId: 'group-2'
  }
}

export const Loading: Story = {
  args: { ...baseArgs, loading: true }
}

export const Empty: Story = {
  args: { ...baseArgs, items: [] }
}

/** How the column looks while "share with everyone" is on: dimmed, nothing clickable. */
export const Disabled: Story = {
  args: {
    ...baseArgs,
    disabled: true,
    selectAll: true,
    selectAllLabel: 'Select all groups',
    selectAllCountLabel: '2 of 40 selected',
    selected: ['group-1', 'group-4']
  }
}

/** Type something that matches nothing to see the not-found text. */
export const NotFound: Story = {
  args: { ...baseArgs, items: groups.slice(0, 3) }
}

/**
 * Select-all row pinned on top of the list, starting partially selected so the dash shows.
 * It always covers the whole list, so filtering the rows does not change what it selects.
 */
export const SelectAll: Story = {
  args: {
    ...baseArgs,
    selectAll: true,
    selectAllLabel: 'Select all groups',
    selectAllCountLabel: '2 of 40 selected',
    selected: ['group-1', 'group-4']
  }
}

/**
 * The row is only *checked* when the caller's "everyone" sentinel is on, which is what clicking
 * the row sets. Note the rows below are ticked too, but that is a consequence, not the cause.
 */
export const SelectAllChecked: Story = {
  args: {
    ...baseArgs,
    selectAll: true,
    selectAllChecked: true,
    selectAllLabel: 'Select all groups',
    selectAllCountLabel: '40 of 40 selected',
    selected: groups.map((group) => group.value)
  }
}

/**
 * Every row ticked one by one, with no sentinel: a different payload, so the row reads
 * indeterminate rather than checked — the same way a group reads indeterminate when its users
 * are picked individually.
 */
export const SelectAllIndividually: Story = {
  args: {
    ...baseArgs,
    selectAll: true,
    selectAllLabel: 'Select all groups',
    selectAllCountLabel: '40 of 40 selected',
    selected: groups.map((group) => group.value)
  }
}

export const TruncatedResults: Story = {
  args: {
    ...baseArgs,
    footerText: 'Showing 40 of 128 results, refine your search'
  }
}

export const WithActions: Story = {
  render: (args) => ({
    components: { AllowedModalColumn, Button },
    setup() {
      const search = ref('')
      const selected = ref<string[]>([])
      const activeId = ref<string | null>(null)
      const toggle = (value: string) => {
        selected.value = selected.value.includes(value)
          ? selected.value.filter((id) => id !== value)
          : [...selected.value, value]
      }
      return { args, search, selected, activeId, toggle }
    },
    template: `
      <div class="flex h-[420px] w-96 gap-6">
        <AllowedModalColumn
          v-bind="args"
          v-model:search="search"
          :selected="selected"
          :active-id="activeId"
          @toggle="toggle"
          @select="activeId = $event"
        >
          <template #actions="{ item }">
            <Button
              icon="arrow-circle-broken-right"
              hierarchy="link-color"
              @click.stop="activeId = item.value"
            />
          </template>
        </AllowedModalColumn>
      </div>
    `
  }),
  args: baseArgs
}
