import { type VariantProps, cva } from 'class-variance-authority'

export { default as Toaster } from './Toaster.vue'
export { default as Toast } from './Toast.vue'
export { toast } from './state'
export type {
  ToastType,
  ToastId,
  ToastCloseReason,
  ToastAction,
  ToastOptions,
  PromiseToastOptions,
  ToastEntry,
  ToastFn
} from './state'

/**
 * Per-type accent applied on top of the generic `Alert` shell via its `class`
 * prop. `cn()`/twMerge lets these override Alert's default border. Every type
 * currently keeps Alert's plain shell; the type indicator is carried by the
 * `FeaturedIconOutline` colour in `Toast.vue`.
 */
export const toastVariants = cva('', {
  variants: {
    type: {
      default: '',
      success: '',
      info: '',
      warning: '',
      error: '',
      loading: ''
    }
  },
  defaultVariants: {
    type: 'default'
  }
})

export type ToastVariants = VariantProps<typeof toastVariants>
