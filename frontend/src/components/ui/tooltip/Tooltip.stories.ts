import type { Meta, StoryObj } from '@storybook/vue3'
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from '@/components/ui/tooltip'
import { Button } from '@/components/ui/button'

const meta = {
  component: TooltipContent,
  title: 'Tooltip',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/FHPNZiT08g7iQysunKZkLm/N%C3%89FIX---ISARD-Design-system-Cliente?node-id=1052-489&m=dev'
    }
  },
  argTypes: {
    title: { control: 'text' },
    subtitle: { control: 'text' },
    side: { control: 'select', options: ['top', 'bottom', 'left', 'right'] },
    align: { control: 'select', options: ['start', 'center', 'end'] },
    arrow: { control: 'boolean' }
  },
  render: (args) => ({
    components: { TooltipContent, Button, TooltipTrigger, Tooltip, TooltipProvider },
    setup() {
      return {
        args
      }
    },
    template: `
      <TooltipProvider>
        <Tooltip :open="true">
          <TooltipTrigger as-child>
            <Button class="mt-10 ml-4">Hover me</Button
          </TooltipTrigger>
          <TooltipContent :title="args.title" :subtitle="args.subtitle" :side="args.side" :align="args.align" :arrow="args.arrow">
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>`
  })
} satisfies Meta<typeof TooltipContent>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any): Story => ({ args: { ...args } })

export const Default = createStory({
  title: 'This is a tooltip',
  subtitle:
    'Tooltips are used to describe or identify an element. In most scenarios, tooltips help the user understand meaning, function or alt-text.'
})
