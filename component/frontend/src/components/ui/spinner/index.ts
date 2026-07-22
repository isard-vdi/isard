import { type VariantProps, cva } from 'class-variance-authority'

export { default as Spinner } from './Spinner.vue'

export const spinnerVariants = cva('animate-spin', {
  variants: {
    size: {
      sm: 'size-4',
      md: 'size-12'
    },
    color: {
      green: 'text-secondary-3-500',
      red: 'text-secondary-2-500'
    }
  },
  defaultVariants: {
    size: 'md',
    color: 'green'
  }
})

export type SpinnerVariants = VariantProps<typeof spinnerVariants>
