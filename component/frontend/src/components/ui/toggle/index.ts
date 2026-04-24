import type { VariantProps } from 'class-variance-authority'
import { cva } from 'class-variance-authority'

export { default as Toggle } from './Toggle.vue'

// Reka's `ToggleGroup` exposes the current item via `data-state="on"`, and
// `Tabs` exposes it via `data-state="active"`. Every active-state rule below is
// duplicated for both attribute values so the same variants can be reused for
// either primitive.
export const toggleVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium hover:bg-muted hover:text-muted-foreground disabled:pointer-events-none disabled:opacity-50 data-[state=on]:bg-accent data-[state=on]:text-accent-foreground data-[state=active]:bg-accent data-[state=active]:text-accent-foreground [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 [&_svg]:shrink-0 focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] outline-none transition-[color,box-shadow] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive whitespace-nowrap",
  {
    variants: {
      variant: {
        default: 'bg-transparent',
        outline:
          'border border-input bg-transparent shadow-sm hover:bg-accent hover:text-accent-foreground',
        success: `
          data-[state=on]:bg-success-800 data-[state=on]:text-base-white
          data-[state=on]:hover:bg-success-900 data-[state=on]:hover:text-base-white
          data-[state=active]:bg-success-800 data-[state=active]:text-base-white
          data-[state=active]:hover:bg-success-900 data-[state=active]:hover:text-base-white
          focus:ring-4 focus:ring-gray
        `,
        'gray-warm': `
          data-[state=on]:bg-gray-warm-600 data-[state=on]:text-base-white
          data-[state=on]:hover:bg-gray-warm-700 data-[state=on]:hover:text-base-white
          data-[state=active]:bg-gray-warm-600 data-[state=active]:text-base-white
          data-[state=active]:hover:bg-gray-warm-700 data-[state=active]:hover:text-base-white
          focus:ring-4 focus:ring-gray
        `,
        error: `
          data-[state=on]:bg-error-700 data-[state=on]:text-base-white
          data-[state=on]:hover:bg-error-800 data-[state=on]:hover:text-base-white
          data-[state=active]:bg-error-700 data-[state=active]:text-base-white
          data-[state=active]:hover:bg-error-800 data-[state=active]:hover:text-base-white
          focus:ring-4 focus:ring-gray
        `,
        'desktops-all': `
          bg-transparent text-gray-warm-500
          hover:bg-sidebar
          focus:ring-4 focus:ring-gray
          data-[state=on]:focus:bg-gray-warm-600 data-[state=on]:focus:text-base-white
          data-[state=on]:bg-gray-warm-600 data-[state=on]:text-base-white
          data-[state=on]:hover:bg-gray-warm-700 data-[state=on]:hover:text-base-white
          data-[state=active]:focus:bg-gray-warm-600 data-[state=active]:focus:text-base-white
          data-[state=active]:bg-gray-warm-600 data-[state=active]:text-base-white
          data-[state=active]:hover:bg-gray-warm-700 data-[state=active]:hover:text-base-white
        `,
        'desktops-persistent': `
          bg-transparent text-gray-warm-500
          hover:bg-sidebar
          focus:ring-4 focus:ring-gray
          data-[state=on]:focus:bg-secondary-3-500 data-[state=on]:focus:text-secondary-3-600
          data-[state=on]:bg-secondary-3-400 data-[state=on]:text-secondary-3-600
          data-[state=on]:hover:bg-secondary-3-600 data-[state=on]:hover:text-gray-warm-50
          data-[state=active]:focus:bg-secondary-3-500 data-[state=active]:focus:text-secondary-3-600
          data-[state=active]:bg-secondary-3-400 data-[state=active]:text-secondary-3-600
          data-[state=active]:hover:bg-secondary-3-600 data-[state=active]:hover:text-gray-warm-50
        `,
        'desktops-temporary': `
          bg-transparent text-gray-warm-500
          hover:bg-sidebar
          focus:ring-4 focus:ring-gray
          data-[state=on]:focus:bg-secondary-1-500 data-[state=on]:focus:text-secondary-1-600
          data-[state=on]:bg-secondary-1-400 data-[state=on]:text-secondary-1-600
          data-[state=on]:hover:bg-secondary-1-600 data-[state=on]:hover:text-gray-warm-50
          data-[state=active]:focus:bg-secondary-1-500 data-[state=active]:focus:text-secondary-1-600
          data-[state=active]:bg-secondary-1-400 data-[state=active]:text-secondary-1-600
          data-[state=active]:hover:bg-secondary-1-600 data-[state=active]:hover:text-gray-warm-50
        `,
        'desktops-deployment': `
          bg-transparent text-gray-warm-500
          hover:bg-sidebar
          focus:ring-4 focus:ring-gray
          data-[state=on]:focus:bg-secondary-2-500 data-[state=on]:focus:text-secondary-2-600
          data-[state=on]:bg-secondary-2-400 data-[state=on]:text-secondary-2-600
          data-[state=on]:hover:bg-secondary-2-600 data-[state=on]:hover:text-gray-warm-50
          data-[state=active]:focus:bg-secondary-2-500 data-[state=active]:focus:text-secondary-2-600
          data-[state=active]:bg-secondary-2-400 data-[state=active]:text-secondary-2-600
          data-[state=active]:hover:bg-secondary-2-600 data-[state=active]:hover:text-gray-warm-50
        `
      },
      size: {
        default: 'h-9 px-2 min-w-9',
        sm: 'h-8 px-1.5 min-w-8',
        lg: 'h-10 px-2.5 min-w-10',
        desktop: 'px-[12px] py-[8px]'
      }
    },
    defaultVariants: {
      variant: 'default',
      size: 'default'
    }
  }
)

export type ToggleVariants = VariantProps<typeof toggleVariants>
