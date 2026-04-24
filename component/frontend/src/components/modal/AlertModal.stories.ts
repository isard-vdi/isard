import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import { AlertModal } from './index'
import Button from '@/components/ui/button/Button.vue'
import { ref } from 'vue'

const meta = {
  component: AlertModal,
  title: 'Modal/AlertModal',
  tags: ['autodocs'],
  argTypes: {
    level: {
      control: 'select',
      options: ['info', 'warning', 'danger'],
      description: 'Visual style of the alert'
    },
    title: {
      control: 'text',
      description: 'Modal title'
    },
    description: {
      control: 'text',
      description: 'Modal description text'
    },
    open: {
      control: 'boolean',
      description: 'Controls modal visibility'
    },
    size: {
      control: 'select',
      options: ['md', 'lg'],
      description: 'Modal width'
    },
    loading: {
      control: 'boolean',
      description: 'Loading state. Blocks user interaction when true.'
    },
    showCloseButton: {
      control: 'boolean',
      description: 'Whether to show the close button at the top-right'
    },
    closeOnBackdropClick: {
      control: 'boolean',
      description: 'Whether clicking outside the modal closes it'
    }
  },
  args: {
    level: 'info',
    title: 'Your desktops have been created',
    description: 'You can now access them from the dashboard.',
    size: 'md',
    loading: false,
    open: false,
    closeOnBackdropClick: true,
    showCloseButton: true
  },
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/FHPNZiT08g7iQysunKZkLm/N%C3%89FIX---ISARD-Design-system-Cliente?node-id=8940-18545&t=iEUFTmYU5t48oIWl-0'
    }
  }
} satisfies Meta<ComponentPropsAndSlots<typeof AlertModal>>

export default meta

type Story = StoryObj<typeof meta>

export const Info: Story = {
  render: (args) => ({
    components: { AlertModal, Button },
    setup() {
      const isOpen = ref(false)
      return { args, isOpen }
    },
    template: `
      <div>
        <Button @click="isOpen = true">Open Modal</Button>
        <AlertModal 
          :open="isOpen"
          @update:open="isOpen = $event"
          :level="args.level"
          :title="args.title"
          :description="args.description"
          :size="args.size"
          :loading="args.loading"
          :closeOnBackdropClick="args.closeOnBackdropClick"
          :showCloseButton="args.showCloseButton"
        >
          <template #footer>
            <Button size="lg" hierarchy="link-color" :disabled="args.loading" @click="isOpen = false">Cancel</Button>
            <Button size="lg" hierarchy="primary" :disabled="args.loading" @click="isOpen = false">Okay</Button>
          </template>
        </AlertModal>
      </div>
    `
  })
}

export const Warning: Story = {
  render: () => ({
    components: { AlertModal, Button },
    setup() {
      const isOpen = ref(false)
      return { isOpen }
    },
    template: `
      <div>
        <Button @click="isOpen = true">Open Warning Modal</Button>
        <AlertModal 
          :open="isOpen"
          @update:open="isOpen = $event"
          level="warning"
          title="Warning. Unsaved changes"
          description="You are about to leave this page. Any unsaved changes will be lost."
          size="lg"
        >
          <template #footer>
            <Button size="lg" hierarchy="link-color" @click="isOpen = false">Cancel</Button>
            <Button size="lg" hierarchy="secondary-gray" @click="isOpen = false">Exit without saving</Button>
            <Button size="lg" hierarchy="primary" @click="isOpen = false">Save and exit</Button>
          </template>
        </AlertModal>
      </div>
    `
  })
}

export const Danger: Story = {
  render: () => ({
    components: { AlertModal, Button },
    setup() {
      const isOpen = ref(false)
      return { isOpen }
    },
    template: `
      <div>
        <Button @click="isOpen = true">Open Danger Modal</Button>
        <AlertModal 
          :open="isOpen"
          @update:open="isOpen = $event"
          level="danger"
          title="You are about to delete this resource"
          description="This action cannot be undone."
          size="md"
        >
          <template #footer>
            <Button size="lg" hierarchy="link-color" @click="isOpen = false">Cancel</Button>
            <Button size="lg" hierarchy="destructive" @click="isOpen = false">Delete</Button>
          </template>
        </AlertModal>
      </div>
    `
  })
}

export const Loading: Story = {
  render: () => ({
    components: { AlertModal, Button },
    setup() {
      const isOpen = ref(false)
      return { isOpen }
    },
    template: `
      <div>
        <Button @click="isOpen = true">Open Loading Modal</Button>
        <AlertModal 
          :open="isOpen"
          @update:open="isOpen = $event"
          level="danger"
          close-on-backdrop-click="true"
          title="Deleting resource"
          description="Please wait while we process your request..."
          size="md"
          :loading="true"
        >
          <template #footer>
            <Button size="lg" hierarchy="link-color" disabled @click="isOpen = false">Cancel</Button>
            <Button size="lg" hierarchy="destructive" disabled @click="isOpen = false">Processing...</Button>
          </template>
        </AlertModal>
      </div>
    `
  })
}
