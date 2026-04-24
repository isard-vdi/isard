import { type VariantProps, cva } from 'class-variance-authority'

export { default as Input } from './Input.vue'

export const inputVariants = cva(
  // Basic input styles - no border, no ring (managed by InputGroup or parent)
  `w-full rounded-md border-0 bg-transparent text-4 p-0 m-0
        placeholder:text-muted-foreground
        focus-visible:outline-none
        disabled:cursor-not-allowed disabled:opacity-50`,
  {
    variants: {}
  }
)

export type InputVariants = VariantProps<typeof inputVariants>
