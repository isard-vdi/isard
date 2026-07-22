import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { Header } from '@/components/header'

const meta = {
  component: Header,
  title: 'Header',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/HqRMn7C5sXLyvVCqQCiJO2/PAU---ISARD-Design-system-Cliente?node-id=9289-17118&m=dev'
    }
  },
  argTypes: {
    title: { control: 'text' },
    subtitle: { control: 'text' }
  },
  render: (args) => ({
    components: { Header },
    setup() {
      return {
        args
      }
    },
    template: `
      <Header
        :title="args.title"
        :subtitle="args.subtitle"
      />`
  })
} satisfies Meta<typeof Header>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const Default = createStory({
  title: 'Lorem ipsum',
  subtitle: 'Dolor sit amet.'
})
