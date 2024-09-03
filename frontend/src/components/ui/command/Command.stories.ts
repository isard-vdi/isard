import type { Meta, StoryObj } from '@storybook/vue3'
import { Command, CommandInput, CommandList, CommandGroup, CommandItem } from '.'

const meta = {
  component: Command,
  title: 'Command',
  tags: ['autodocs'],
  render: (args) => ({
    components: { Command, CommandInput, CommandList, CommandGroup, CommandItem },
    setup() {
      return {
        args
      }
    },
    template: `
    <Command :open="args.open">
      <CommandInput :placeholder="args.placeholder" />
      <CommandList>
        <CommandGroup>
          <CommandItem v-for="item in args.items" :key="item.id" :value="item.id">{{ item.name }}</SelectItem>
        </CommandGroup>
      </CommandList>
    </Select>
    `
  })
} satisfies Meta<typeof Command> & {
  placeholder: String
  items: Array<{ id: string; name: string }>
  open: boolean
}

export default meta
type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const Default = createStory({
  placeholder: 'Default',
  items: [
    {
      id: 'nefix',
      name: 'Néfix Estrada'
    },
    {
      id: 'olivia',
      name: 'Olivia Rhye'
    }
  ],
  open: false
})

export const Focus = createStory({ ...Default.args }, { pseudo: { focus: true } })
export const Open = createStory({ ...Default.args, open: true }, { pseudo: { focus: true } })
