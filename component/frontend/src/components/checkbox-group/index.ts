import { type VariantProps, cva } from 'class-variance-authority'

export { default as CheckboxGroup } from './CheckboxGroup.vue'

export const checkboxGroupItemVariants = cva(
  `
    flex bg-base-white rounded-xl p-4 border border-gray-warm-300 cursor-pointer transition-colors
    flex-col justify-center hover:border-brand-700 hover:ring-xs hover:ring-brand
  `,

  {
    variants: {
      kind: {
        'featured-icon': '',
        card: '',
        text: '',
        image: ''
      },
      selected: {
        true: 'border-brand-700',
        false: ''
      },
      disabled: {
        true: 'opacity-50 hover:border-gray-warm-300 hover:cursor-not-allowed',
        false: ''
      },
      loading: {
        true: 'cursor-wait',
        false: ''
      }
    },
    defaultVariants: {
      kind: 'text',
      selected: false,
      disabled: false,
      loading: false
    }
  }
)

export type CheckboxGroupItemVariants = VariantProps<typeof checkboxGroupItemVariants>
