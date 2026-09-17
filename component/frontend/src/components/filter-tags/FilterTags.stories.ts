import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { ref } from 'vue'
import { FilterTags, type FilterCategory } from '.'

const categories: FilterCategory[] = [
  {
    key: 'kind',
    label: 'Type',
    options: [
      { value: 'persistent', label: 'Persistents', count: 12 },
      { value: 'volatile', label: 'Temporaries', count: 3 },
      { value: 'deployment', label: 'Deployments', count: 5 }
    ]
  },
  {
    key: 'status',
    label: 'Status',
    options: [
      { value: 'started', label: 'Started', count: 4 },
      { value: 'stopped', label: 'Stopped', count: 16 }
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
