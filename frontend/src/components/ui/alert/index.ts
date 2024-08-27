import { type VariantProps, cva } from 'class-variance-authority'

export { default as Alert } from './Alert.vue'
export { default as AlertTitle } from './AlertTitle.vue'
export { default as AlertDescription } from './AlertDescription.vue'

export const alertVariants = cva(
  `relative w-full
  rounded-xl p-[16px] border border-gray-warm-300
  text-sm
  [&>svg~*]:pl-7 [&>svg+div]:translate-y-[-3px] [&>svg]:absolute [&>svg]:left-4 [&>svg]:top-4 [&>svg]:text-foreground`,
  {
    variants: {
      variant: {
        default: 'bg-background text-foreground',
        destructive: 'border-error-300 bg-error-25'
      }
    },
    defaultVariants: {
      variant: 'default'
    }
  }
)

export type AlertVariants = VariantProps<typeof alertVariants>
