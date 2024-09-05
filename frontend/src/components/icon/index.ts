import { type VariantProps, cva } from 'class-variance-authority'

export { default as Icon } from './Icon.vue'

export const iconVariants = cva('', {
  variants: {
    size: {
      sm: 'h-[16px] w-[16px]',
      md: 'h-[20px] w-[20px]',
      lg: 'h-[24px] w-[24px]',
      xl: 'h-[28px] w-[28px]'
    }
  },
  defaultVariants: {
    size: 'md'
  }
})

export type IconVariants = VariantProps<typeof iconVariants>
