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
          bg-brand-700 text-base-white border-brand-700 border
          hover:bg-brand-800 :hover:text-base-white
          focused:ring-ring-brand-shadow-xs focused:rounded-xl
          disabled:bg-gray-warm-100 disabled:text-gray-warm-400 disabled:border-gray-warm-200
        `,
        'secondary-gray': `
          bg-base-white text-gray-warm-700 border-gray-warm-300 border
          hover:bg-gray-warm-50 :hover:text-gray-warm-800
          disabled:bg-base-white disabled:text-gray-warm-400 disabled:border-gray-warm-200
        `,
        'secondary-color': `
          bg-base-white text-brand-700 border-brand-700 border
          hover:bg-gray-warm-50 :hover:text-brand-700
          disabled:bg-base-white disabled:text-gray-warm-400 disabled:border-gray-warm-200

        `,
        'tertiary-color': 
        `
          bg-base-white text-gray-warm-600 border-warning-300 border
          hover:warning-300 :hover:text-gray-warm-50
          disabled:bg-base-white disabled:text-gray-warm-400 disabled:border-gray-warm-200
        `,
        'link-gray':
        `
          text-gray-warm-600
          disabled:text-gray-warm-400
        `,
        'link-color':
        `
          text-brand-700
          disabled:text-gray-warm-400
        `,
        // default: 'bg-primary text-primary-foreground hover:bg-primary/90',

        // destructive:
        //   'bg-destructive text-destructive-foreground hover:bg-destructive/90',
        // outline:
        //   'border border-input bg-background hover:bg-accent hover:text-accent-foreground',
        // secondary:
        //   'bg-secondary text-secondary-foreground hover:bg-secondary/80',
        // ghost: 'hover:bg-accent hover:text-accent-foreground',
        // link: 'text-primary underline-offset-4 hover:underline',
      },
      size: {
        sm: 'px-[12px] py-[8px] text-sm',
        md: 'px-[14px] py-[10px] text-sm',
        lg: 'px-[16px] py-[10px] text-md',
        xl: 'px-[18px] py-[12px] text-md',
        '2xl': 'px-[22px] py-[16px] text-lg',
      },
    },
    defaultVariants: {
      hierarchy: 'primary',
      size: 'md',
    },
  },
)

export type ButtonVariants = VariantProps<typeof buttonVariants>
