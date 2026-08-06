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
    placeholder: { control: 'text' },
    previewCount: { control: 'number' },
    maxResults: { control: 'number' },
    maxVisibleTags: { control: 'number' },
    tagsDisplay: { control: 'select', options: ['wrap', 'scroll'] },
    disabled: { control: 'boolean' },
    invalid: { control: 'boolean' }
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
    template: `<SearchableTags
      v-model="modelValue"
      :tags="args.tags"
      :placeholder="args.placeholder"
      :preview-count="args.previewCount"
      :max-results="args.maxResults"
      :max-visible-tags="args.maxVisibleTags"
      :tags-display="args.tagsDisplay"
      :disabled="args.disabled"
      :invalid="args.invalid"
    />`
  })
} satisfies Meta<ComponentPropsAndSlots<typeof SearchableTags>>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args: { ...args },
  parameters: { ...parameters }
})

const manyTags = Array.from({ length: 100 }, (x, i) => {
  const tagNum = i + 1
  return { label: `Tag ${tagNum}`, value: `tag${tagNum}` }
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

/** Long list: the dropdown caps results and hints that the search must be refined. */
export const ManyOptions = createStory({
  modelValue: [],
  tags: manyTags,
  placeholder: 'Select tags'
})

/** Overflow collapsed into "+N" once more than `maxVisibleTags` are selected. */
export const WrapOverflow = createStory({
  modelValue: ['tag1', 'tag2', 'tag3', 'tag4', 'tag5', 'tag6', 'tag7', 'tag8'],
  tags: manyTags,
  placeholder: 'Select tags',
  tagsDisplay: 'wrap'
})

/** Same selection kept on a single horizontally scrollable row. */
export const ScrollOverflow = createStory({
  modelValue: ['tag1', 'tag2', 'tag3', 'tag4', 'tag5', 'tag6', 'tag7', 'tag8'],
  tags: manyTags,
  placeholder: 'Select tags',
  tagsDisplay: 'scroll'
})

/** Long labels stay truncated instead of stretching the control. */
export const LongLabels = createStory({
  modelValue: ['long1', 'long2', 'long3', 'long4'],
  tags: [
    { label: 'ubuntu-24.04.1-desktop-amd64-with-a-very-long-name.iso', value: 'long1' },
    { label: 'debian-12.5.0-amd64-netinst-extended-edition.iso', value: 'long2' },
    { label: 'windows-11-enterprise-evaluation-23h2-x64.iso', value: 'long3' },
    { label: 'fedora-workstation-live-x86_64-40-1.14.iso', value: 'long4' }
  ],
  placeholder: 'Select tags'
})
