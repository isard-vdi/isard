import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { LoginProviderForm } from '@/components/login'

const meta = {
  component: LoginProviderForm,
  title: 'Login/LoginProviderForm',
  tags: ['autodocs']
} satisfies Meta<typeof LoginProviderForm>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const Default = createStory({})
