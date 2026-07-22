import type { Meta, StoryObj } from '@storybook/vue3-vite'
import Modal from './Modal.vue'
import Button from '@/components/ui/button/Button.vue'
import { ref } from 'vue'

interface ModalProps {
  title?: string
  description?: string
  showCloseButton?: boolean
  closeButtonColor?: string
  open?: boolean
  class?: string
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '3xl' | '4xl' | 'full'
  closeOnBackdropClick?: boolean
}

const meta: Meta<ModalProps> = {
  title: 'Modal/Modal',
  component: Modal,
  parameters: {
    layout: 'centered'
  },
  tags: ['autodocs'],
  argTypes: {
    title: {
      control: 'text',
      description: 'Modal title'
    },
    description: {
      control: 'text',
      description: 'Modal description'
    },
    showCloseButton: {
      control: 'boolean',
      description: 'Show close button'
    },
    closeButtonColor: {
      control: 'text',
      description: 'Close button icon color. Orange by default'
    },
    open: {
      control: 'boolean',
      description: 'Modal visibility'
    },
    size: {
      control: 'select',
      options: ['sm', 'md', 'lg', 'xl', '2xl', '3xl', '4xl', 'full'],
      description: 'Modal maximum width'
    },
    closeOnBackdropClick: {
      control: 'boolean',
      description: 'Whether clicking outside the modal closes it'
    }
  },
  args: {
    title: 'Modal Title',
    description: 'This is a description for the modal.',
    showCloseButton: true,
    closeButtonColor: 'secondary-2-500',
    open: false,
    size: 'lg',
    closeOnBackdropClick: true
  }
} satisfies Meta<ModalProps>

export default meta
type Story = StoryObj<ModalProps>

export const Default: Story = {
  render: (args) => ({
    components: { Modal, Button },
    setup() {
      const isOpen = ref(false)
      return { args, isOpen }
    },
    template: `
      <div>
        <Button @click="isOpen = true">Open Modal</Button>
        <Modal 
          :title="args.title"
          :description="args.description"
          :showCloseButton="args.showCloseButton"
          :closeButtonColor="args.closeButtonColor"
          :open="isOpen"
          :size="args.size"
          :closeOnBackdropClick="args.closeOnBackdropClick"
          @close="isOpen = false"
        >
          <p>This is modal content. You can add any content here.</p>
          
          <template #footer>
            <div class="flex w-full justify-center items-center pb-5 gap-2">
              <Button hierarchy="secondary-gray" @click="isOpen = false">Cancel</Button>
              <Button hierarchy="primary" @click="isOpen = false">Confirm</Button>
            </div>
          </template>
        </Modal>
      </div>
    `
  })
}

export const Small: Story = {
  ...Default,
  args: {
    ...meta.args,
    size: 'sm'
  }
}

export const Medium: Story = {
  ...Default,
  args: {
    ...meta.args,
    size: 'md'
  }
}

export const Large: Story = {
  ...Default,
  args: {
    ...meta.args,
    size: 'lg'
  }
}

export const ExtraLarge: Story = {
  ...Default,
  args: {
    ...meta.args,
    size: 'xl'
  }
}

export const DoubleExtraLarge: Story = {
  ...Default,
  args: {
    ...meta.args,
    size: '2xl'
  }
}

export const TripleExtraLarge: Story = {
  ...Default,
  args: {
    ...meta.args,
    size: '3xl'
  }
}

export const QuadrupleExtraLarge: Story = {
  ...Default,
  args: {
    ...meta.args,
    size: '4xl'
  }
}

export const Full: Story = {
  ...Default,
  args: {
    ...meta.args,
    size: 'full'
  }
}
