import type { Meta, StoryObj } from '@storybook/vue3'
import { LoginCategorySelect } from '@/components/login'

const meta = {
  component: LoginCategorySelect,
  title: 'LoginCategorySelect',
  tags: ['autodocs'],
  argTypes: {
    categories: Array<{ id: string; name: string; photo: string }>
  }
} satisfies Meta<typeof LoginCategorySelect>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const Default = createStory({
  categories: [
    { name: 'category 1', id: '111111', photo: 'https://via.placeholder.com/150' },
    { name: 'category 2', id: '222222', photo: 'https://via.placeholder.com/150' },
    { name: 'category 3', id: '333333', photo: 'https://via.placeholder.com/150' },
    { name: 'category 4', id: '444444', photo: 'https://via.placeholder.com/150' },
    { name: 'category 5', id: '555555', photo: 'https://via.placeholder.com/150' }
  ]
})

export const TwoColumns = createStory({
  categories: [
    { name: 'category 1', id: '111111', photo: 'https://via.placeholder.com/150' },
    { name: 'category 2', id: '222222', photo: 'https://via.placeholder.com/150' },
    { name: 'category 3', id: '333333', photo: 'https://via.placeholder.com/150' },
    { name: 'category 4', id: '444444', photo: 'https://via.placeholder.com/150' },
    { name: 'category 5', id: '555555', photo: 'https://via.placeholder.com/150' },
    { name: 'category 6', id: '666666', photo: 'https://via.placeholder.com/150' }
  ]
})
