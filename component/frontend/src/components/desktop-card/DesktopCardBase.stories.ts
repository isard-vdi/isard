import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'

import { DesktopCardBase, cardSizes } from '@/components/desktop-card'
import { InputField } from '@/components/input-field'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'

const meta = {
  component: DesktopCardBase,
  title: 'Desktop Card/DesktopCardBase',
  tags: ['autodocs', 'DesktopCard'],
  parameters: {
    design: {
      type: 'figma',
      url: ''
    }
  },
  argTypes: {
    desktopKind: {
      control: 'select',
      options: ['persistent', 'nonpersistent', 'deployment']
    },
    imageUrl: { control: 'text' },
    showNetworkOverlay: { control: 'boolean' },
    size: {
      control: 'select',
      options: [...cardSizes]
    }
  },
  render: (args) => ({
    components: {
      DesktopCardBase,
      InputField,
      Textarea,
      Button
    },
    setup() {
      return { args }
    },
    template: `
      <DesktopCardBase :desktop-kind="args.desktopKind" :image-url="args.imageUrl" :show-network-overlay="args.showNetworkOverlay" :size="args.size">
        <template #header-actions>
          <Button icon="image-plus" hierarchy="secondary-gray" size="sm" />
        </template>
        <template #header>
          <InputField placeholder="Desktop Name" />
          <Textarea
            class="bg-base-white resize-none"
            placeholder="Desktop Description"
          />
        </template>
        <template #footer>
          <Button
            icon="play"
            hierarchy="secondary-gray"
            class="aspect-square rounded-full"
            disabled
          />
        </template>
      </DesktopCardBase>
    `
  })
} satisfies Meta<ComponentPropsAndSlots<typeof DesktopCardBase>>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args: {
    imageUrl: `https://${window.location.hostname}:443/assets/img/desktops/stock/15.jpg`,
    ...args
  },
  parameters: { ...parameters }
})

export const ForForm = createStory({
  desktopKind: 'persistent',
  size: 'lg'
})

export const Size2xs = createStory({ desktopKind: 'persistent', size: '2xs' })
export const SizeXs = createStory({ desktopKind: 'persistent', size: 'xs' })
export const SizeSm = createStory({ desktopKind: 'persistent', size: 'sm' })
export const SizeMd = createStory({ desktopKind: 'persistent', size: 'md' })
export const SizeLg = createStory({ desktopKind: 'persistent', size: 'lg' })
export const SizeXl = createStory({ desktopKind: 'persistent', size: 'xl' })
