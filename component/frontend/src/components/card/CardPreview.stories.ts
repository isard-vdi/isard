import type { Meta, StoryObj } from '@storybook/vue3-vite'
import CardPreview from './CardPreview.vue'
import mountains from '@/assets/img/mountains.svg'

const meta: Meta<typeof CardPreview> = {
  title: 'Card/CardPreview',
  component: CardPreview,
  tags: ['autodocs']
}

export default meta

export const Default: StoryObj<typeof meta> = {
  render: () => ({
    components: { CardPreview },
    template: `<div class="w-full flex justify-center"><CardPreview /></div>`,
    backgroundImage: mountains
  })
}
