import type { Meta, StoryObj } from '@storybook/vue3'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'

const meta = {
  component: Avatar,
  title: 'Avatar',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/FHPNZiT08g7iQysunKZkLm/N%C3%89FIX---ISARD-Design-system-Cliente?node-id=1152-89351'
    }
  },
  argTypes: {
    size: { control: 'select', options: ['xs', 'sm', 'md', 'lg', 'xl', '2xl'] },
    shape: { control: 'select', options: ['circle', 'square'] }
  },
  render: (args) => ({
    components: { Avatar, AvatarFallback, AvatarImage },
    setup() {
      return {
        args
      }
    },
    template: `
      <Avatar
        :size="args.size"
        :shape="args.shape"
      >
        <AvatarImage src="https://gravatar.com/avatar/c052ebd55dd78dcb2af1e6e02bc58e2d009460efc84928adb97059aed586088c?d=identicon" alt="@radix-vue" />
        <AvatarFallback>JD</AvatarFallback>
      </Avatar>`
  })
} satisfies Meta<typeof Avatar>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const Circle = createStory({
  size: 'md',
  shape: 'circle'
})

export const Square = createStory({
  size: 'md',
  shape: 'square'
})
