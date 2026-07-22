import { type VariantProps, cva } from 'class-variance-authority'

export { default as Icon } from './Icon.vue'
export { default as CopyIcon } from './CopyIcon.vue'
// Note: If CopyIcon causes Storybook docgen issues, import directly: import CopyIcon from '@/components/icon/CopyIcon.vue'

export const iconVariants = cva('', {
  variants: {
    size: {
      xs: 'h-[14px] w-[14px]',
      sm: 'h-4 w-4',
      md: 'h-5 w-5',
      lg: 'h-6 w-6',
      xl: 'h-[28px] w-[28px]',
      xxl: 'h-[36px] w-[36px]'
    }
  },
  defaultVariants: {
    size: 'md'
  }
})

export type IconVariants = VariantProps<typeof iconVariants>
