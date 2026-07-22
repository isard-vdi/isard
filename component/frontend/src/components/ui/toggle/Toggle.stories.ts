import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { Toggle } from '@/components/ui/toggle'
import type { Component } from 'vue'
import { BadgeMini } from '@/components/badge/mini'

const meta = {
  component: Toggle,
  title: 'Toggle/Toggle',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/HqRMn7C5sXLyvVCqQCiJO2/PAU---ISARD-Design-system-Cliente?node-id=9289-17118&m=dev'
    }
  },
  argTypes: {
    variant: {
      control: 'select',
      options: [
        'default',
        'outline',
        'desktops-all',
        'desktops-persistent',
        'desktops-temporary',
        'desktops-deployments'
      ]
    },
    size: {
      control: 'select',
      options: ['default', 'sm', 'lg']
    }
  }
} satisfies Meta<typeof Toggle>

export default meta

type Story = StoryObj<typeof meta>

function createStory(options: {
  args: Story['args']
  template?: string
  components?: Record<string, Component>
  parameters?: Story['parameters']
}): Story {
  const template = options.template ?? 'Toggle'
  return {
    args: options.args,
    render: (args) => ({
      components: { Toggle, ...options.components },
      setup() {
        return {
          args
        }
      },
      template: `
        <Toggle 
          v-bind="args"
        >
          <template #default="slotProps">
            ${template}
          </template>
        </Toggle>`
    }),
    parameters: options.components
  }
}

export const Default = createStory({
  args: {
    variant: 'outline',
    size: 'default'
  }
})

export const Success = createStory({
  args: {
    variant: 'success',
    size: 'default'
  }
})
export const Error = createStory({
  args: {
    variant: 'error',
    size: 'default'
  }
})
export const GrayWarm = createStory({
  args: {
    variant: 'gray-warm',
    size: 'default'
  }
})

export const DesktopsAll = createStory({
  args: {
    variant: 'desktops-all',
    size: 'desktop'
  },
  template: `All <BadgeMini name="all" :selected="slotProps.pressed" value="2" />`,
  components: { BadgeMini }
})

export const DesktopsPersistent = createStory({
  args: {
    variant: 'desktops-persistent',
    size: 'desktop'
  },
  template: `Persistent <BadgeMini name="persistent" :selected="slotProps.pressed" value="2" />`,
  components: { BadgeMini }
})

export const DesktopsTemporary = createStory({
  args: {
    variant: 'desktops-temporary',
    size: 'desktop'
  },
  template: `Temporary <BadgeMini name="temporary" :selected="slotProps.pressed" value="2" />`,
  components: { BadgeMini }
})

export const DesktopsDeployments = createStory({
  args: {
    variant: 'desktops-deployment',
    size: 'desktop'
  },
  template: `Deployments <BadgeMini name="deployment" :selected="slotProps.pressed" value="5" />`,
  components: { BadgeMini }
})
