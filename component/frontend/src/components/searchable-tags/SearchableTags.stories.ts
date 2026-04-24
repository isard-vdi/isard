import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import { ref, watch } from 'vue'
import { SearchableTags } from '.'

const meta = {
  component: SearchableTags,
  title: 'SearchableTags',
  tags: ['autodocs'],
  argTypes: {
    modelValue: { control: 'array' },
    tags: { control: 'array' },
    placeholder: { control: 'text' }
  },
  render: (args) => ({
    components: { SearchableTags },
    setup() {
      const modelValue = ref(args.modelValue)

      // Watch for changes from Storybook controls
      watch(
        () => args.modelValue,
        (newValue) => {
          modelValue.value = newValue
        }
      )

      return {
        args,
        modelValue
      }
    },
    template: `<SearchableTags v-model="modelValue" :tags="args.tags" :placeholder="args.placeholder" />`
  })
} satisfies Meta<ComponentPropsAndSlots<typeof SearchableTags>>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args: { ...args },
  parameters: { ...parameters }
})

export const Default = createStory({
  modelValue: ['tag1', 'tag3'],
  tags: [
    { label: 'Tag 1', value: 'tag1' },
    { label: 'Tag 2', value: 'tag2' },
    { label: 'Tag 3', value: 'tag3' },
    { label: 'Tag 4', value: 'tag4' }
  ],
  placeholder: 'Select tags'
})

export const Scrollable = createStory({
  modelValue: ['tag1', 'tag2', 'tag3', 'tag4', 'tag5', 'tag6', 'tag7', 'tag8'],
  tags: Array.from({ length: 100 }, (x, i) => {
    const tagNum = i + 1
    return { label: `Tag ${tagNum}`, value: `tag${tagNum}` }
  }),
  placeholder: 'Select tags'
})
