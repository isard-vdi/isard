import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { ScrollToTop } from '.'

const meta = {
  component: ScrollToTop,
  title: 'Page/ScrollToTop',
  tags: ['autodocs'],
  parameters: {
    backgrounds: {
      default: 'base-background',
      values: [{ name: 'base-background', value: '#fbf8ee' }]
    }
  },
  argTypes: {
    threshold: {
      control: 'number',
      description:
        'Distance, in pixels, the page has to travel before the button shows up. Zero shows it as ' +
        'soon as the page leaves the top.'
    }
  },
  render: (args) => ({
    components: { ScrollToTop },
    setup: () => ({ args }),
    template: `
      <div class="h-[300vh] p-8 text-gray-warm-600">
        Scroll the preview down to reveal the button.
        <div class="fixed bottom-6 right-6 flex flex-col items-end gap-3">
          <ScrollToTop v-bind="args" />
        </div>
      </div>
    `
  })
} satisfies Meta<typeof ScrollToTop>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {}
}

export const LateAppearance: Story = {
  args: { threshold: 400 }
}
