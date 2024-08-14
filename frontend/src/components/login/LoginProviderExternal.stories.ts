import type { StoryObj } from '@storybook/vue3'
import { LoginProviderExternal, Provider } from '@/components/login'

const meta = {
  component: LoginProviderExternal,
  title: 'LoginProviderExternal',
  tags: ['autodocs'],
  argTypes: {
    provider: { control: 'select', options: Provider }
  }
}

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const Google = createStory({
  provider: Provider.Google
})

export const SAML = createStory({
  provider: Provider.SAML
})

export const GoogleWithCustomText = createStory({
  provider: Provider.Google,
  text: 'Això és una prova amb Google!'
})
export const SAMLWithCustomText = createStory({
  provider: Provider.SAML,
  text: 'Això és una prova amb SAML!'
})
