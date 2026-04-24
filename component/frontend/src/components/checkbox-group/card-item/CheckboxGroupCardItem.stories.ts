import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { ref, watch } from 'vue'
import { CheckboxGroupCardItem } from '@/components/checkbox-group/card-item'
import regenerateUrlsImg from '@/assets/img/modal/regenerate-urls.svg'
import keepUrlsImg from '@/assets/img/modal/keep-urls.svg'

const meta: Meta<typeof CheckboxGroupCardItem> = {
  component: CheckboxGroupCardItem,
  title: 'Checkbox/CheckboxGroupCardItem',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/atbFgukhep1rQlPtZLDAbm/ISARD-Design-system-Cliente?node-id=124-2838'
    }
  },
  argTypes: {
    loading: { control: 'boolean', defaultValue: false },
    isSelected: { control: 'boolean', defaultValue: false },
    disabled: { control: 'boolean', defaultValue: false },
    item: { control: 'object' }
  },
  render: (args) => ({
    components: { CheckboxGroupCardItem },
    setup() {
      const isSelected = ref(args.isSelected)
      watch(
        () => args.isSelected,
        (v) => {
          isSelected.value = v
        }
      )
      const handleCheck = () => {
        isSelected.value = !isSelected.value
      }
      return { args, isSelected, handleCheck }
    },
    template:
      '<CheckboxGroupCardItem v-bind="args" :is-selected="isSelected" @check="handleCheck" />'
  })
}
export default meta

type Story = StoryObj<typeof meta>

export const RegenerateUrls: Story = {
  args: {
    loading: false,
    isSelected: false,
    disabled: false,
    item: {
      icon: 'link-broken-01',
      title: 'Regenerate URLs',
      image: regenerateUrlsImg,
      description:
        'Reset the deployment links. Previously generated links will no longer be available. Download the CSV file.',
      value: 'regenerate'
    }
  }
}

export const SelectedKeepUrls: Story = {
  args: {
    loading: false,
    isSelected: true,
    disabled: false,
    item: {
      icon: 'equal',
      title: 'Keep URLs',
      image: keepUrlsImg,
      description: 'Keep the links and download the CSV file.',
      value: 'keep'
    }
  }
}

export const DisabledState: Story = {
  args: {
    loading: false,
    isSelected: false,
    disabled: true,
    item: {
      icon: 'link-broken-01',
      title: 'Regenerate URLs',
      image: regenerateUrlsImg,
      description:
        'Reset the deployment links. Previously generated links will no longer be available. Download the CSV file.',
      value: 'regenerate'
    }
  }
}

export const LoadingState: Story = {
  args: {
    loading: true,
    isSelected: false,
    disabled: false,
    item: {
      icon: 'link-broken-01',
      title: 'Loading...',
      image: '',
      description: '',
      value: 'loading'
    }
  }
}
