import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem
} from '@/components/ui/dropdown-menu'
import Button from '@/components/ui/button/Button.vue'
import Icon from '@/components/icon/Icon.vue'

const meta = {
  component: DropdownMenu,
  title: 'Dropdown/DropdownMenu',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/FHPNZiT08g7iQysunKZkLm/N%C3%89FIX---ISARD-Design-system-Cliente?node-id=8940-18816&m=dev'
    }
  },
  argTypes: {},
  render: (args) => ({
    components: {
      DropdownMenu,
      DropdownMenuTrigger,
      DropdownMenuContent,
      DropdownMenuGroup,
      DropdownMenuItem,
      Button,
      Icon
    },
    setup() {
      return {
        args
      }
    },
    template: `
        <DropdownMenu>
          <DropdownMenuTrigger>
            <div class="bg-white border border-[#D7D3D0] rounded-lg p-2">
              <Icon size="lg" name="dots-vertical" />
            </div>
        </DropdownMenuTrigger>
          <DropdownMenuContent >
            <DropdownMenuGroup class="bg-base-white">
                <DropdownMenuItem >
                  <Button hierarchy="link-gray" icon="edit-01" iconSize="md">Edit deployment</Button>
                </DropdownMenuItem>
                <DropdownMenuItem >
                  <Button hierarchy="link-gray" icon="download-02"  iconSize="md">Download direct viewer</Button>
                </DropdownMenuItem>
                <DropdownMenuItem >
                  <Button hierarchy="link-gray" icon="link-01" iconSize="md">Direct link</Button>
                </DropdownMenuItem>
                <DropdownMenuItem >
                  <Button hierarchy="link-gray" icon="refresh-cw-04" iconSize="md">Recreate deployment</Button>
                </DropdownMenuItem>
                <DropdownMenuItem >
                  <Button hierarchy="link-gray" icon="calendar" iconSize="md">Reservation</Button>
                </DropdownMenuItem>                
                <DropdownMenuItem >
                  <Button hierarchy="link-gray" icon="trash-04" iconSize="md">Delete</Button>
                </DropdownMenuItem>
            </DropdownMenuGroup>
          </DropdownMenuContent >
        </DropdownMenu>`
  })
} satisfies Meta<ComponentPropsAndSlots<typeof DropdownMenu>>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const Default = createStory({})
