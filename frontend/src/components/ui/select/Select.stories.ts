import type { Meta, StoryObj } from '@storybook/vue3'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectGroup, SelectItem } from '.'

const meta = {
  component: Select,
  title: 'Select',
  tags: ['autodocs'],
  render: (args) => ({
    components: { Select, SelectValue, SelectTrigger, SelectContent, SelectGroup, SelectItem },
    setup() {
      return {
        args
      }
    },
    template: `
    <Select :open="args.open">
      <SelectTrigger>
        <SelectValue :placeholder="args.placeholder" />
      </SelectTrigger>
      <SelectContent>
        <SelectGroup>
          <SelectItem v-for="item in args.items" :key="item.id" :value="item.id">{{ item.name }}</SelectItem>
        </SelectGroup>
      </SelectContent>
    </Select>
    `
  })
} satisfies Meta<typeof Select> & {
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
