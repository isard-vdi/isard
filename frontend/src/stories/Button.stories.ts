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
    },
  },
  argTypes: {
    // TODO: Use buttonVariants
    variant: { control: 'select', options: ['primary', 'secondary-gray', 'secondary-color', 'tertiary-color', 'link-gray', 'link-color'] },
    // TODO: Use buttonVariants
    size: { control: 'select', options: ['sm', 'md', 'lg', 'xl', '2xl' ] },
    disabled: { control: 'boolean' },
  },
  render: (args) => ({
    components: { Button },
    setup() {
      return {
        args
      }
    },
    template: `<Button :variant="args.variant" :size="args.size" :disabled="args.disabled">Button CTA</Button>`
  })
} satisfies Meta<typeof Button>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  args: {
    variant: 'primary'
  },
};

export const SecondaryGray: Story = {
  args: {
    variant: 'secondary-gray'
  },
};

export const SecondaryColor: Story = {
  args: {
    variant: 'secondary-color'
  },
};

export const TertiaryColor: Story = {
  args: {
    variant: 'tertiary-color'
  },
};

export const LinkGray: Story = {
  args: {
    variant: 'link-gray'
  },
};

export const LinkColor: Story = {
  args: {
    variant: 'link-color'
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
    size: '2xl'
  },
};

export const PrimaryDisabled: Story = {
  args: {
    variant: 'primary',
    disabled: true
  },
};

export const SecondaryGrayDisabled: Story = {
  args: {
    variant: 'secondary-gray',
    disabled: true
  },
};

export const SecondaryColorDisabled: Story = {
  args: {
    variant: 'secondary-color',
    disabled: true
  },
};

export const TertiaryColorDisabled: Story = {
  args: {
    variant: 'tertiary-color',
    disabled: true
  },
};

export const LinkGrayDisabled: Story = {
  args: {
    variant: 'link-gray',
    disabled: true
  },
};

export const LinkColorDisabled: Story = {
  args: {
    variant: 'link-color',
    disabled: true
  },
};