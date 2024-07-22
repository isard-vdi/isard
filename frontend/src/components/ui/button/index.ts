import { type VariantProps, cva } from 'class-variance-authority'

export { default as Button } from './Button.vue'

export const buttonVariants = cva(
  // Common classes applied to all buttons
  `
    inline-flex items-center justify-center whitespace-nowrap
    rounded-md font-semibold
  `,
  {
    variants: {
      hierarchy: {
        primary: `
          bg-brand-700 text-base-white
          hover:bg-brand-800 :hover:text-base-white
          focus:ring focus:ring-brand
          disabled:bg-gray-warm-100 disabled:text-gray-warm-400 disabled:border-gray-warm-200
        `,
        'secondary-gray': `
          bg-base-white text-gray-warm-700 border-gray-warm-300 border
          hover:bg-gray-warm-50 :hover:text-gray-warm-800
          focus:ring focus:ring-gray
          disabled:bg-base-white disabled:text-gray-warm-400 disabled:border-gray-warm-200
        `,
        'secondary-color': `
          bg-base-white text-brand-700 border-brand-700 border
          hover:bg-gray-warm-50 :hover:text-brand-700
          focus:ring focus:ring-brand
          disabled:bg-base-white disabled:text-gray-warm-400 disabled:border-gray-warm-200

        `,
        'tertiary-color': `
          bg-base-white text-gray-warm-600 border-warning-300 border
          hover:warning-300 :hover:text-gray-warm-50
          focus:ring focus:ring-warning
          disabled:bg-base-white disabled:text-gray-warm-400 disabled:border-gray-warm-200
        `,
        'link-gray': `
          text-gray-warm-600
          hover:underline
          disabled:text-gray-warm-400
        `,

        'link-color': `
          text-brand-700
          hover:underline
          disabled:text-gray-warm-400
        `,
        destructive: `
          bg-error-600 text-base-white border-error-600 border
          hover:bg-error-700 :hover:text-base-white
          focus:ring focus:ring-error
          disabled:bg-gray-warm-100 disabled:text-gray-warm-400 disabled:border-gray-warm-200
        `
      },
      size: {
        sm: 'px-[12px] py-[8px] text-sm',
        md: 'px-[14px] py-[10px] text-sm',
        lg: 'px-[16px] py-[10px] text-md',
        xl: 'px-[18px] py-[12px] text-md',
        '2xl': 'px-[22px] py-[16px] text-lg'
      }
    },
    defaultVariants: {
      hierarchy: 'primary',
      size: 'md'
    }
  }
)

export type ButtonVariants = VariantProps<typeof buttonVariants>
