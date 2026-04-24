import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { AvatarLabel } from '.'

const meta = {
  component: AvatarLabel,
  title: 'Avatar/AvatarLabel',
  tags: ['autodocs'],
  argTypes: {
    shape: {
      control: 'select',
      options: ['circle', 'square']
    },
    size: {
      control: 'select',
      options: ['xs', 'sm', 'md', 'lg', 'xl', '2xl']
    },
    src: {
      control: 'text'
    },
    name: {
      control: 'text'
    },
    sub: {
      control: 'text'
    }
  },
  render: (args) => ({
    components: { AvatarLabel },
    setup() {
      return { args }
    },
    template: `<AvatarLabel v-bind="args" />`
  })
} satisfies Meta<typeof AvatarLabel>

export default meta

type Story = StoryObj<typeof meta>

const createStory =
  (o: { name: string; sub: string; src: string; fallback?: string }) =>
  (size: Story['args']['size']): Story => ({
    args: {
      name: o.name,
      sub: o.sub,
      size,
      src: o.src
    }
  })

const createOliviaRhye = createStory({
  name: 'Olivia Rhye',
  sub: 'olivia.rhye',
  src: 'https://gravatar.com/avatar/c052ebd55dd78dcb2af1e6e02bc58e2d009460efc84928adb97059aed586088c?d=identicon'
})
const createNoImage = createStory({
  name: 'Not Olivia',
  sub: 'not.olivia',
  fallback: 'NO',
  src: 'https://example.com/invalid-image.png'
})

export const extraSmall = createOliviaRhye('xs')
export const small = createOliviaRhye('sm')
export const smallNoImage = createNoImage('sm')
export const medium = createOliviaRhye('md')
export const mediumNoImage = createNoImage('md')
export const large = createOliviaRhye('lg')
export const extraLarge = createOliviaRhye('xl')
export const doubleExtraLarge = createOliviaRhye('2xl')
