import { type VariantProps, cva } from 'class-variance-authority'

export { default as NavbarItem } from './NavbarItem.vue'

export const navbarItemVariants = cva(
  `
    px-[12px] py-[8px] rounded-sm 
    grid grid-rows-1 grid-flow-col gap-x-[12px] justify-start items-center
    focus:ring
  `,
  {
    variants: {
      current: {
        false: `
          bg-base-menu
          font-[600] text-gray-warm-600
          hover:bg-base-menu-hover
        `,
        true: `
          bg-base-menu-current
          font-[800] text-gray-warm-800
          focus:ring-gray-secondary
        `
      },
      collapsed: {
        false: `w-[272px]`,
        true: ``
      }
    },
    defaultVariants: {
      current: false,
      collapsed: false
    }
  }
)

export type NavbarItemVariants = VariantProps<typeof navbarItemVariants>
