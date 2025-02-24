import { cva, type VariantProps } from 'class-variance-authority'

export { default as Avatar } from './Avatar.vue'
export { default as AvatarFallback } from './AvatarFallback.vue'
export { default as AvatarImage } from './AvatarImage.vue'

export const avatarVariant = cva(
  `
    inline-flex items-center justify-center font-normal text-foreground select-none shrink-0 bg-secondary overflow-hidden
    aspect-square

    border-[0.75px] border-solid border-base-black/8
    bg-gray-warm-100

    focus:ring-4 focus:ring-gray
  `,
  {
    variants: {
      size: {
        xs: 'h-[24px] text-xs',
        sm: 'h-[32px] text-sm',
        md: 'h-[40px] text-md',
        lg: 'h-[48px] text-lg',
        xl: 'h-[56px] text-xl',
        '2xl': 'h-[64px] text-xl'
      },
      shape: {
        circle: 'rounded-full',
        square: 'rounded-xl'
      }
    },
    defaultVariants: {
      size: 'md',
      shape: 'circle'
    }
  }
)

export type AvatarVariants = VariantProps<typeof avatarVariant>
