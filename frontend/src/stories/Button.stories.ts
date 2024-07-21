import type { Meta, StoryObj } from '@storybook/vue3';
import { fn } from '@storybook/test';
import Button from '../components/ui/button/Button.vue';
import { buttonVariants } from '@/components/ui/button';

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
    label: { control: 'text' },
    // TODO: Use buttonVariants
    hierarchy: { control: 'select', options: ['primary', 'secondary-gray', 'secondary-color', 'tertiary-color', 'link-gray', 'link-color', 'destructive'] },
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
    template: `<Button :hierarchy="args.hierarchy" :size="args.size" :disabled="args.disabled">{{ args.label }}</Button>`
  })
} satisfies Meta<typeof Button>;

export default meta;

type Story = StoryObj<typeof meta>;

const createStory = (args: any, parameters?: any): Story => ({args: { ...args, label: 'Button CTA' }, parameters: { ...parameters } });

export const Primary = createStory({ hierarchy: 'primary' });
export const SecondaryGray = createStory({ hierarchy: 'secondary-gray' });
export const SecondaryColor = createStory({ hierarchy: 'secondary-color' });
export const TertiaryColor = createStory({ hierarchy: 'tertiary-color' }); 
export const LinkGray = createStory({ hierarchy: 'link-gray' });
export const LinkColor = createStory({ hierarchy: 'link-color' });
export const destructive = createStory({ hierarchy: 'destructive' });
export const Small = createStory({ size: 'sm' });
export const Medium = createStory({ size: 'md' });
export const Large = createStory({ size: 'lg' });
export const ExtraLarge = createStory({ size: 'xl' });
export const ExtraExtraLarge = createStory({ size: '2xl' });
export const PrimaryDisabled = createStory({ ...Primary.args, disabled: true });
export const SecondaryGrayDisabled = createStory({ ...SecondaryGray.args, disabled: true });
export const SecondaryColorDisabled = createStory({ ...SecondaryColor.args, disabled: true });
export const TertiaryColorDisabled = createStory({ ...TertiaryColor.args, disabled: true });
export const LinkGrayDisabled = createStory({ ...LinkGray.args, disabled: true });
export const LinkColorDisabled = createStory({ ...LinkColor.args, disabled: true });

// Pseudo states: hover, focus
export const PrimaryHover = createStory({ ...Primary.args }, { pseudo: { hover: true }});
export const SecondaryGrayHover = createStory({ ...SecondaryGray.args }, { pseudo: { hover: true }});
export const SecondaryColorHover = createStory({ ...SecondaryColor.args }, { pseudo: { hover: true }});
export const TertiaryColorHover = createStory({ ...TertiaryColor.args }, { pseudo: { hover: true }});
export const LinkGrayHover = createStory({ ...LinkGray.args }, { pseudo: { hover: true }});
export const LinkColorHover = createStory({ ...LinkColor.args }, { pseudo: { hover: true }});
export const DestructiveHover = createStory({ ...destructive.args }, { pseudo: { hover: true }});

export const PrimaryFocus = createStory({ ...Primary.args }, { pseudo: { focus: true }});
export const SecondaryGrayFocus = createStory({ ...SecondaryGray.args }, { pseudo: { focus: true }});
export const SecondaryColorFocus = createStory({ ...SecondaryColor.args }, { pseudo: { focus: true }});
export const TertiaryColorFocus = createStory({ ...TertiaryColor.args }, { pseudo: { focus: true }});
export const LinkGrayFocus = createStory({ ...LinkGray.args }, { pseudo: { focus: true }});
export const LinkColorFocus = createStory({ ...LinkColor.args }, { pseudo: { focus: true }});
export const DestructiveFocus = createStory({ ...destructive.args }, { pseudo: { focus: true }});