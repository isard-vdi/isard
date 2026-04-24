export { default as Sidebar } from './Sidebar.vue'
export { default as SidebarToggle } from './SidebarToggle.vue'

import { type VariantProps, cva } from 'class-variance-authority'

export const sidebarVariants = cva(
  // base-menu renders from the index.css theme
  ``
)

export type SidebarVariants = VariantProps<typeof sidebarVariants>

export const sidebarItemsContainer = `
  p-2
  flex flex-col gap-3
`

export const sidebarItemVariants = cva(
  `
    w-full rounded-sm 
    flex flex-row gap-x-3 justify-start items-center
    focus:ring-3 ring-[#1018280d] text-base
  `,
  {
    variants: {
      selected: {
        false: `
          bg-base-menu
          font-medium text-gray-warm-600
        `,
        true: `
          bg-base-menu-current
          font-extrabold text-gray-warm-800
          focus:ring-gray-secondary
        `
      }
    },
    defaultVariants: {
      selected: false
    }
  }
)

export type SidebarItemVariants = VariantProps<typeof sidebarItemVariants>
