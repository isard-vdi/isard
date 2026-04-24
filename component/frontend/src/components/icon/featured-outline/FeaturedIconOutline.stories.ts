import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'

const meta = {
  component: FeaturedIconOutline,
  title: 'Icon/FeaturedIconOutline',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/FHPNZiT08g7iQysunKZkLm/N%C3%89FIX---ISARD-Design-system-Cliente?node-id=4843-410985&m=dev'
    }
  },
  argTypes: {
    color: {
      control: 'select',
      options: ['brand', 'gray', 'error', 'warning', 'success', 'temporary', 'persistent'],
      defaultValue: 'persistent'
    },
    size: {
      control: 'select',
      options: ['sm', 'md', 'lg', 'xl']
    },
    name: {
      control: 'text'
    },
    class: {
      control: 'text'
    },
    iconClass: {
      control: 'text'
    },
    kind: {
      control: 'select',
      options: ['outline', 'filled'],
      defaultValue: 'filled'
    }
  },
  render: (args) => ({
    components: { FeaturedIconOutline },
    setup() {
      return {
        args
      }
    },
    template: `
      <FeaturedIconOutline
        v-bind="args"
      />
    `
  })
} satisfies Meta<typeof FeaturedIconOutline>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const Default = createStory({})

export const Brand = createStory({
  color: 'brand',
  size: 'md'
})
export const Gray = createStory({
  color: 'gray',
  size: 'md'
})
export const Error = createStory({
  color: 'error',
  size: 'md'
})
export const Warning = createStory({
  color: 'warning',
  size: 'md'
})
export const Success = createStory({
  color: 'success',
  size: 'md'
})

export const BrandFilled = createStory({
  color: 'brand',
  size: 'md',
  kind: 'filled'
})
export const GrayFilled = createStory({
  color: 'gray',
  size: 'md',
  kind: 'filled'
})
export const ErrorFilled = createStory({
  color: 'error',
  size: 'md',
  kind: 'filled'
})
export const WarningFilled = createStory({
  color: 'warning',
  size: 'md',
  kind: 'filled'
})
export const SuccessFilled = createStory({
  color: 'success',
  size: 'md',
  kind: 'filled'
})

export const TemporaryFilled = createStory({
  color: 'temporary',
  size: 'md',
  kind: 'filled'
})

export const PersistentFilled = createStory({
  color: 'persistent',
  size: 'md',
  kind: 'filled'
})
