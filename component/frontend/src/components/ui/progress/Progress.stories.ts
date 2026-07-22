import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { Progress } from '.'

const meta = {
  component: Progress,
  title: 'Progress',
  tags: ['autodocs'],
  render: (args) => ({
    components: { Progress },
    setup() {
      return {
        args
      }
    },
    template: `<div style="max-width: 300px"><Progress v-bind="args" :class="'bg-gray-warm-300 ' + args.class" /></div>`
  })
} satisfies Meta<typeof Progress>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (percent: number, cls = ''): Story => ({
  args: { modelValue: percent, class: cls }
})

export const _50percent = createStory(50)
export const _0percent = createStory(0)
export const _100percent = createStory(100)
export const _40percentBlue = createStory(40, 'text-info-400')
