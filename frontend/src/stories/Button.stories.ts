import type { Meta, StoryObj } from '@storybook/vue3';
import { fn } from '@storybook/test';
import Button from '../components/ui/button/Button.vue';
import { buttonVariants } from '../components/ui/button/index';

const meta = {
  component: Button,
  title: 'Button',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/FHPNZiT08g7iQysunKZkLm/N%C3%89FIX---ISARD-Design-system-Cliente?node-id=3466-410043&m=dev'
      // url: 'https://www.figma.com/design/FHPNZiT08g7iQysunKZkLm/N%C3%89FIX---ISARD-Design-system-Cliente?node-id=1-1183&m=dev'
    },
  },
  argTypes: {
    // TODO: Use buttonVariants
    variant: { control: 'select', options: ['primary', 'secondaryGray', 'linkColor'] },
    // TODO: Use buttonVariants
    size: { control: 'select', options: ['sm', 'md', 'lg', 'xl', 'xxl' ] },
  },
  render: (args) => ({
    components: { Button },
    setup() {
      return {
        args
      }
    },
    template: `<Button :variant="args.variant" :size="args.size">Button</Button>`
  })
} satisfies Meta<typeof Button>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  args: {},
};

export const Secondary: Story = {
  args: {
    variant: 'secondaryColor'
  },
};

export const Small: Story = {
  args: {
    size: 'sm'
  },
};

export const Medium: Story = {
  args: {
    size: 'md'
  },
};

export const Large: Story = {
  args: {
    size: 'lg'
  },
};

export const ExtraLarge: Story = {
  args: {
    size: 'xl'
  },
};

export const ExtraExtraLarge: Story = {
  args: {
    size: 'xxl'
  },
};
