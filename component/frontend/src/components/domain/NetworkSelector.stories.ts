import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import { ref, watch } from 'vue'
import NetworkSelector from './NetworkSelector.vue'

const meta = {
  component: NetworkSelector,
  title: 'Domain/NetworkSelector',
  tags: ['autodocs'],
  argTypes: {
    modelValue: { control: 'array' },
    options: { control: 'array' },
    requiredIds: { control: 'array' },
    placeholder: { control: 'text' },
    previewCount: { control: 'number' },
    maxResults: { control: 'number' },
    disabled: { control: 'boolean' },
    invalid: { control: 'boolean' }
  },
  render: (args) => ({
    components: { NetworkSelector },
    setup() {
      const modelValue = ref(args.modelValue)

      watch(
        () => args.modelValue,
        (newValue) => {
          modelValue.value = newValue
        }
      )

      return { args, modelValue }
    },
    template: `<NetworkSelector
      v-model="modelValue"
      :options="args.options"
      :required-ids="args.requiredIds"
      :placeholder="args.placeholder"
      :preview-count="args.previewCount"
      :max-results="args.maxResults"
      :disabled="args.disabled"
      :invalid="args.invalid"
    />`
  })
} satisfies Meta<ComponentPropsAndSlots<typeof NetworkSelector>>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any): Story => ({ args: { ...args } })

const options = [
  { id: 'default', name: 'Default' },
  { id: 'wireguard', name: 'Wireguard' },
  { id: 'personal', name: 'Personal' },
  { id: 'lab-vlan-101', name: 'Lab VLAN 101' }
]

export const Default = createStory({
  modelValue: ['default', 'wireguard'],
  options,
  placeholder: 'Add networks'
})

/** Nothing picked: the domain gets no network interface at all. */
export const Empty = createStory({
  modelValue: [],
  options,
  placeholder: 'Add networks'
})

/** A single interface has no order to set, so the reorder hint stays hidden. */
export const SingleNetwork = createStory({
  modelValue: ['default'],
  options,
  placeholder: 'Add networks'
})

/** Wireguard flagged because a viewer or the bastion depends on it. */
export const WithRequired = createStory({
  modelValue: ['default', 'wireguard', 'personal'],
  options,
  requiredIds: ['wireguard'],
  placeholder: 'Add networks'
})

/** Long list: the picker caps results and hints that the search must be refined. */
export const ManyOptions = createStory({
  modelValue: ['default'],
  options: [
    ...options,
    ...Array.from({ length: 60 }, (_, i) => ({ id: `vlan-${i}`, name: `VLAN ${i + 200}` }))
  ],
  placeholder: 'Add networks'
})
