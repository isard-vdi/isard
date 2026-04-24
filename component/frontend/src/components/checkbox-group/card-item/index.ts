import { type VariantProps, cva } from 'class-variance-authority'

export { default as CheckboxGroupCardItem, type CardItem } from './CheckboxGroupCardItem.vue'

export const checkboxGroupCardVariants = cva(
  `
  max-w-[365px] rounded-xl overflow-hidden p-0 justify-start items-start transition-all
  focus-within:outline-hidden focus-within:ring-sm focus-within:ring-offset-0 focus-within:ring-4
  focus-within:ring-gray-warm-100
  `,
  {
    variants: {
      disabled: {
        true: 'bg-gray-warm-50',
        false: ''
      },
      selected: {
        true: 'border-2 border-brand-700 focus-within:border-brand-700 focus-within:ring-brand',
        false: ''
      }
    }
  }
)

export type CardItemVariants = VariantProps<typeof checkboxGroupCardVariants>
