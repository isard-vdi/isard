import type { Meta, StoryObj } from '@storybook/vue3'
import { LoginLayout } from '@/layouts/login'

const meta = {
  component: LoginLayout,
  title: 'Layouts/Login',
  tags: ['autodocs']
} satisfies Meta<typeof LoginLayout>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const FullLogin = createStory({
  version: 'v12.3.0'
})

export const WithoutVersion = createStory({})
