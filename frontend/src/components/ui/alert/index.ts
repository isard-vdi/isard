import { type VariantProps, cva } from 'class-variance-authority'

export { default as Alert } from './Alert.vue'
export { default as AlertTitle } from './AlertTitle.vue'
export { default as AlertDescription } from './AlertDescription.vue'

export const alertVariants = cva(
  `relative w-full
  rounded-xl p-[16px] border border-gray-warm-300
  shadow-sm text-sm
  [&>svg]:absolute [&>svg]:left-[16px] [&>svg]:top-[16px] [&>svg]:m-[10px] [&>svg~*]:ml-[56px]
  [&>img]:absolute [&>img]:left-[16px] [&>img]:top-[16px] [&>img]:m-[10px] [&>img~*]:ml-[56px]`,
  {
    variants: {
      variant: {
        default: 'bg-base-white text-foreground',
        destructive: 'border-error-300 bg-error-25'
      }
    },
    defaultVariants: {
      variant: 'default'
    }
  }
)

export type AlertVariants = VariantProps<typeof alertVariants>
