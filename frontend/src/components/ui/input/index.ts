import { cva, type VariantProps } from 'class-variance-authority'

export { default as Input } from './Input.vue'

export const inputVariants = cva(
  // TODO: Correct the total height of the input substrating the border
  // Common classes applied to all inputs
  `w-full rounded-md border-[1px] border-gray-warm-300
        bg-background text-[16px] leading-[24px] ring-offset-background
        placeholder:text-muted-foreground
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2
        disabled:cursor-not-allowed disabled:opacity-50`,
  {
    variants: {
      size: {
        sm: 'px-[12px] py-[8px]',
        md: 'px-[14px] py-[10px]'
      },
      destructive: {
        false: ``,
        true: `border-error-600 focus:ring-error`
      }
    },
    defaultVariants: {
      size: 'sm',
      destructive: false
    }
  }
)

export type InputVariants = VariantProps<typeof inputVariants>
