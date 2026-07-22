import type { Meta, StoryObj } from '@storybook/vue3-vite'
import InputField from './InputField.vue'

const meta = {
  title: 'Input/InputField',
  component: InputField,
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/kZGlXBMDzC0kVb3BMl7j7x/NAOMI--ISARD-Design-system-Cliente?node-id=1090-57817&t=roTNzkdHmR5V5ghC-4'
    }
  },
  tags: ['autodocs'],
  argTypes: {
    modelValue: {
      control: 'text',
      description: 'Input value (v-model)'
    },
    placeholder: {
      control: 'text',
      description: 'Placeholder text'
    },
    icon: {
      control: 'text',
      description: 'Icon name to display on the left'
    },
    type: {
      control: 'select',
      options: ['text', 'email', 'password', 'number', 'tel', 'url'],
      description: 'HTML Input type'
    },
    destructive: {
      control: 'boolean',
      description: 'Show error state with red border, red ring on focus, and alert icon',
      default: false
    },
    disabled: {
      control: 'boolean',
      description: 'Disable the input',
      default: false
    }
  },
  render: (args) => ({
    components: { InputField },
    setup() {
      return { args }
    },
    template: '<div class="w-96"><InputField v-bind="args" /></div>'
  })
} satisfies Meta<typeof InputField>

export default meta
type Story = StoryObj<typeof meta>

const createStory = (args: Story['args'] = {}): Story => ({
  args
})

export const Default = createStory({
  placeholder: 'Enter text...'
})

export const WithIcon = createStory({
  placeholder: 'Search...',
  icon: 'search-lg'
})

export const Email = createStory({
  placeholder: 'email@example.com',
  icon: 'mail-01',
  type: 'email'
})

export const Password = createStory({
  placeholder: 'Enter password...',
  icon: 'lock-02',
  type: 'password'
})

export const Destructive = createStory({
  placeholder: 'Password',
  destructive: true,
  type: 'password'
})

export const DestructiveWithIcon = createStory({
  placeholder: 'Password',
  icon: 'lock-02',
  destructive: true,
  type: 'password'
})

export const Disabled = createStory({
  placeholder: 'Disabled input',
  icon: 'lock-02',
  disabled: true
})

export const Showcase: Story = {
  render: () => ({
    components: { InputField },
    setup() {
      return {}
    },
    template: `
      <div class="flex flex-col gap-6 w-96">
        <div>
          <label class="text-sm font-medium mb-2 block">Default</label>
          <InputField placeholder="Enter text..." />
        </div>

        <div>
          <label class="text-sm font-medium mb-2 block">With Icon</label>
          <InputField placeholder="Search..." icon="search-lg" />
        </div>

        <div>
          <label class="text-sm font-medium mb-2 block">Email</label>
          <InputField placeholder="email@example.com" type="email" icon="mail-01" />
        </div>

        <div>
          <label class="text-sm font-medium mb-2 block">Password</label>
          <InputField placeholder="Enter password..." type="password" icon="lock-02" />
        </div>

        <div>
          <label class="text-sm font-medium mb-2 block">Error</label>
          <InputField placeholder="Password" type="password" destructive />
        </div>

        <div>
          <label class="text-sm font-medium mb-2 block">Disabled</label>
          <InputField placeholder="Disabled input" icon="lock-02" disabled />
        </div>
      </div>
    `
  })
}
