import { cva, type VariantProps } from 'class-variance-authority'

export { default as AlertModal } from './AlertModal.vue'
export { default as Modal } from './Modal.vue'
export { default as QuotaExceededModal } from './QuotaExceededModal.vue'

export const modalVariants = cva('', {
  variants: {
    level: {
      warning: 'bg-[hsl(43,100%,47%)] text-gray-warm-900',
      danger: 'bg-error-600 text-red-900',
      info: 'bg-[hsl(212,48%,52%)] text-blue-900',
      success: 'bg-[hsl(152,56%,40%)] text-green-900'
    },
    size: {
      md: 'min-w-96',
      lg: 'min-w-140'
    }
  },
  defaultVariants: {
    level: 'info',
    size: 'md'
  }
})

export type ModalVariants = VariantProps<typeof modalVariants>
