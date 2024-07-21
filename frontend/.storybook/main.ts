import type { StorybookConfig } from '@storybook/vue3-vite'

const config: StorybookConfig = {
  stories: ['../src/**/*.mdx', '../src/**/*.stories.@(js|jsx|mjs|ts|tsx)'],
  addons: [
    '@storybook/addon-onboarding',
    '@storybook/addon-links',
    '@storybook/addon-essentials',
    '@chromatic-com/storybook',
    '@storybook/addon-interactions',
    '@storybook/addon-designs',
    "storybook-addon-pseudo-states"
  ],
  framework: {
    name: '@storybook/vue3-vite',
    options: {}
  },
  core: {
    disableTelemetry: true
  },
}
export default config
