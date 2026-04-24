import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { ToggleGroup, ToggleGroupItem } from '.'
import { Icon } from '@/components/icon'

const meta = {
  component: ToggleGroup,
  title: 'Toggle/ToggleGroup',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/HqRMn7C5sXLyvVCqQCiJO2/PAU---ISARD-Design-system-Cliente?node-id=9289-17118&m=dev'
    }
  }
} satisfies Meta<typeof ToggleGroup>

export default meta

type Story = StoryObj<typeof meta>

function createStory(template: string, components: any = {}): Story {
  return {
    render: () => ({
      components: { ToggleGroup, ToggleGroupItem, ...components },
      template
    })
  }
}

export const Desktops = createStory(`
  <ToggleGroup :spacing="1" type="single" size="default" class="bg-base-white border border-1-5 border-gray-warm-300 p-1 rounded-lg">
    <ToggleGroupItem value="all" variant="gray-warm" selected>
      All
    </ToggleGroupItem>
    <ToggleGroupItem value="on" variant="success">
      On
    </ToggleGroupItem>
    <ToggleGroupItem value="off" variant="error">
      Off
    </ToggleGroupItem>
  </ToggleGroup>
`)

export const Templates = createStory(
  `
    <ToggleGroup :spacing="1" type="single" size="default">
      <ToggleGroupItem value="mine" variant="gray-warm">
        <Icon name="user-03" strokeColor="" />My templates
      </ToggleGroupItem>
      <ToggleGroupItem value="shared" variant="gray-warm">
        <Icon name="share-06" strokeColor="" />Shared templates
      </ToggleGroupItem>
    </ToggleGroup>
  `,
  { Icon }
)
