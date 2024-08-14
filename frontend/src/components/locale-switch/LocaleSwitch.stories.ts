import type { Meta, StoryObj } from '@storybook/vue3'
import { LocaleSwitch } from '.'

const meta = {
  component: LocaleSwitch,
  title: 'LocaleSwitch',
  tags: ['autodocs']
} satisfies Meta<typeof LocaleSwitch>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const Default = createStory({})
