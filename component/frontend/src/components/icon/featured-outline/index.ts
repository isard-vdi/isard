import { type VariantProps, cva } from 'class-variance-authority'

export { default as FeaturedIconOutline } from './FeaturedIconOutline.vue'

const colors = {
  current: 'text-current',
  brand: 'text-brand-600',
  gray: 'text-gray-warm-600',
  error: 'text-error-600',
  warning: 'text-warning-600',
  success: 'text-success-600',
  temporary: 'text-secondary-1-600',
  persistent: 'text-secondary-3-600',
  deployment: 'text-secondary-2-600'
} as const

export const featuredIconOutlineVariants = cva('', {
  variants: {
    color: colors,
    kind: { outline: '', filled: '' }
  },
  defaultVariants: {
    color: 'current',
    kind: 'outline'
  }
})

const standardColors = ['current', 'brand', 'gray', 'error', 'warning', 'success'] as const

export const featuredIconLayerVariants = cva('aspect-square rounded-full', {
  variants: {
    kind: { outline: '', filled: '' },
    layer: { outer: '', inner: '' },
    color: Object.fromEntries(Object.keys(colors).map((k) => [k, '']))
  },
  compoundVariants: [
    { kind: 'outline', layer: 'inner', class: 'border-2 p-[3px] border-current/30' },
    { kind: 'outline', layer: 'outer', class: 'border-2 p-[3px] border-current/10' },
    ...standardColors.flatMap((color) => [
      { kind: 'filled' as const, layer: 'inner' as const, color, class: 'p-[7px] bg-current/10' },
      { kind: 'filled' as const, layer: 'outer' as const, color, class: 'p-[6px] bg-current/5' }
    ]),
    { kind: 'filled', layer: 'inner', color: 'temporary', class: 'p-[7px] bg-secondary-1-500' },
    { kind: 'filled', layer: 'outer', color: 'temporary', class: 'p-[6px] bg-secondary-1-400' },
    { kind: 'filled', layer: 'inner', color: 'persistent', class: 'p-[7px] bg-secondary-3-500' },
    { kind: 'filled', layer: 'outer', color: 'persistent', class: 'p-[6px] bg-secondary-3-400' },
    { kind: 'filled', layer: 'inner', color: 'deployment', class: 'p-[7px] bg-secondary-2-500' },
    { kind: 'filled', layer: 'outer', color: 'deployment', class: 'p-[6px] bg-secondary-2-400' }
  ],
  defaultVariants: { kind: 'outline', layer: 'outer' }
})

export type FeaturedIconOutlineVariants = VariantProps<typeof featuredIconOutlineVariants>
