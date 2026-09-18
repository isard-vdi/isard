import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { ref } from 'vue'
import { FilterTags, type FilterCategory } from '.'

const categories: FilterCategory[] = [
  {
    key: 'kind',
    label: 'Type',
    options: [
      { value: 'persistent', label: 'Persistents', count: 12, tone: 'persistent', icon: 'browser' },
      { value: 'volatile', label: 'Temporaries', count: 3, tone: 'nonpersistent', icon: 'clock' },
      {
        value: 'deployment',
        label: 'Deployments',
        count: 5,
        tone: 'deployment',
        icon: 'layout-alt-04'
      }
    ]
  },
  {
    key: 'status',
    label: 'Status',
    options: [
      { value: 'started', label: 'Started', count: 4, icon: 'play' },
      { value: 'stopped', label: 'Stopped', count: 16, icon: 'stop' }
    ]
  }
]

const meta = {
  component: FilterTags,
  title: 'FilterTags',
  tags: ['autodocs'],
  argTypes: {
    categories: { control: 'object', description: 'Filter categories and their options.' }
  },
  render: (args) => ({
    components: { FilterTags },
    setup: () => {
      const selected = ref<Record<string, string[]>>(args.modelValue ?? { kind: [], status: [] })
      return { args, selected }
    },
    template: `
      <div class="w-[420px] p-8">
        <FilterTags v-model="selected" :categories="args.categories" />
      </div>
    `
  })
} satisfies Meta<typeof FilterTags>

export default meta

type Story = StoryObj<typeof meta>

export const Empty: Story = {
  args: { categories, modelValue: { kind: [], status: [] } }
}

export const WithTags: Story = {
  args: { categories, modelValue: { kind: ['persistent'], status: ['started'] } }
}

/** Narrow enough to push tags out of the row: the counter opens the panel. */
export const Narrow: Story = {
  args: {
    categories,
    modelValue: {
      kind: ['persistent', 'volatile', 'deployment'],
      status: ['started', 'stopped']
    }
  },
  render: (args) => ({
    components: { FilterTags },
    setup: () => {
      const selected = ref<Record<string, string[]>>(args.modelValue ?? { kind: [], status: [] })
      return { args, selected }
    },
    template: `
      <div class="w-[320px] p-8">
        <FilterTags v-model="selected" :categories="args.categories" />
      </div>
    `
  })
}

/** Every tone at once: the kinds in their colour, the rest neutral. */
export const EveryTone: Story = {
  args: {
    categories,
    modelValue: {
      kind: ['persistent', 'volatile', 'deployment'],
      status: ['started', 'stopped']
    }
  },
  render: (args) => ({
    components: { FilterTags },
    setup: () => {
      const selected = ref<Record<string, string[]>>(args.modelValue ?? { kind: [], status: [] })
      return { args, selected }
    },
    template: `
      <div class="w-[900px] p-8">
        <FilterTags v-model="selected" :categories="args.categories" />
      </div>
    `
  })
}
