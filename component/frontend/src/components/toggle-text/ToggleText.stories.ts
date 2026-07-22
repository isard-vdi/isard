import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import { ToggleText } from '@/components/toggle-text'
import { setup } from '@storybook/vue3-vite'
import { createI18n } from 'vue-i18n'
import es from '@/locales/es-ES.json'
import ca from '@/locales/ca-ES.json'
import en from '@/locales/en-US.json'

const i18n = createI18n({
  legacy: false,
  locale: 'es',
  fallbackLocale: 'en',
  messages: {
    es,
    ca,
    en
  }
})

setup((app) => {
  app.use(i18n)
})

const meta = {
  component: ToggleText,
  title: 'Toggle/ToggleText',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/FHPNZiT08g7iQysunKZkLm/N%C3%89FIX---ISARD-Design-system-Cliente?node-id=9163-98690&t=0QEhThFKd6fZdwQK-1'
    }
  },
  argTypes: {
    left: { control: 'object' },
    right: { control: 'object' }
  },
  render: (args) => ({
    components: { ToggleText },
    setup() {
      return { args }
    },
    template: `
      <ToggleText :left="args.left" :right="args.right" />
    `
  })
} satisfies Meta<ComponentPropsAndSlots<typeof ToggleText>>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args: { ...args },
  parameters: { ...parameters }
})

export const Default = createStory({
  left: {
    value: 'left',
    label: 'components.toggletext.toggle.left'
  },
  right: {
    value: 'right',
    label: 'components.toggletext.toggle.right'
  }
})
