import { type VariantProps, cva } from 'class-variance-authority'

export { default as Select } from './Select.vue'
export { default as SelectContent } from './SelectContent.vue'
export { default as SelectGroup } from './SelectGroup.vue'
export { default as SelectItem } from './SelectItem.vue'
export { default as SelectItemText } from './SelectItemText.vue'
export { default as SelectLabel } from './SelectLabel.vue'
export { default as SelectScrollDownButton } from './SelectScrollDownButton.vue'
export { default as SelectScrollUpButton } from './SelectScrollUpButton.vue'
export { default as SelectSeparator } from './SelectSeparator.vue'
export { default as SelectTrigger } from './SelectTrigger.vue'
export { default as SelectValue } from './SelectValue.vue'

export const selectTriggerVariants = cva(
  `
  flex items-center justify-between
  h-10 w-full px-[14px] py-[10px] rounded-md
  border border-gray-warm-300 bg-base-white
  text-md leading-md text-gray-warm-900 font-medium
  data-placeholder:text-gray-warm-500 [&[data-placeholder])]:font-regular
  focus:border-gray-warm-700 focus:ring-3 focus:ring-brand
  outline-hidden
  disabled:cursor-not-allowed disabled:opacity-50
  [&>span]:line-clamp-1
`,
  {
    variants: {
      hierarchy: {
        primary: '',
        destructive: 'ring-3 ring-error'
      }
    },
    defaultVariants: {
      hierarchy: 'primary'
    }
  }
)

export type SelectTriggerVariants = VariantProps<typeof selectTriggerVariants>
