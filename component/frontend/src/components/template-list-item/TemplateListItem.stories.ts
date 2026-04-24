import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import TemplateListItem from './TemplateListItem.vue'

const meta = {
  component: TemplateListItem,
  title: 'ListItem/TemplateListItem',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma'
    },
    layout: 'centered'
  },
  argTypes: {},
  render: (args) => ({
    components: { TemplateListItem },
    setup() {
      return { args }
    },
    template: `<div class="w-full"><TemplateListItem v-bind="args" /></div>`
  })
} satisfies Meta<ComponentPropsAndSlots<typeof TemplateListItem>>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: Partial<ComponentPropsAndSlots<typeof TemplateListItem>>): Story => ({
  args
})

export const Default = createStory({
  name: 'Ubuntu 22.04 Desktop',
  description: 'Image for Ubuntu 22.04.',
  userName: 'John Doe'
})

export const LongName = createStory({
  name: 'Debian 12 with CUDA, TensorFlow, PyTorch and complete data science toolkit for machine learning operations',
  description: 'Debian 12 with data science and ML tools.',
  userName: 'Lorem Ipsum'
})

export const LongDescription = createStory({
  name: 'CentOS 8 Server',
  description:
    'CentOS 8 Server optimized for high-performance computing. Includes Apache, MySQL, PHP, Node.js, Docker, Kubernetes, and various development frameworks. Pre-configured for scalability and security with optimized settings for enterprise environments.',
  userName: 'Foo Bar'
})
