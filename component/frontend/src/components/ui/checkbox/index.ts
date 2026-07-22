import { type VariantProps, cva } from 'class-variance-authority'

export { default as Checkbox } from './Checkbox.vue'

export const checkboxVariants = cva(
  `
    text-base-white mt-0 flex items-center justify-center border-input aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive shrink-0 border shadow-xs transition-shadow outline-none
    hover:ring-[3px] hover:ring-brand-200 focus-visible:ring-brand-200 focus-visible:ring-[3px]
    disabled:cursor-not-allowed disabled:hover:ring-gray-warm-300 disabled:focus-visible:ring-gray-warm-300
    data-[state=checked]:bg-brand-700 data-[state=checked]:border-brand-700
    data-[state=checked]:disabled:border-gray-warm-300 data-[state=checked]:disabled:bg-gray-warm-50
  `,
  {
    variants: {
      indeterminate: {
        true: `
          data-[state=indeterminate]:bg-brand-700 data-[state=indeterminate]:border-brand-700
          data-[state=indeterminate]:disabled:border-gray-warm-300 data-[state=indeterminate]:disabled:bg-gray-warm-50
        `,
        false: ``
      },
      type: {
        checkbox: `rounded-sm`,
        radio: `rounded-full`
      },
      size: {
        sm: `size-4`,
        md: `size-5`
      },
      textPosition: {
        before: `order-2`,
        after: `order-1`
      }
    },
    defaultVariants: {
      type: 'checkbox',
      size: 'md'
    }
  }
)

export type CheckboxVariants = VariantProps<typeof checkboxVariants>
