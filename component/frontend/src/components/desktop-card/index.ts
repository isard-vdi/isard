import type { InjectionKey } from 'vue'
import { cva } from 'class-variance-authority'

// --- Component exports ---

export { default as DesktopCard } from './DesktopCard.vue'
export { default as DesktopCardBase } from './DesktopCardBase.vue'
export { default as DesktopCardBaseStacked } from './DesktopCardBaseStacked.vue'
export { default as DesktopCardSkeleton } from './DesktopCardSkeleton.vue'

export { default as DesktopCardHeaderActions } from './parts/DesktopCardHeaderActions.vue'
export { default as DesktopCardHeaderActionsDropdownContent } from './parts/DesktopCardHeaderActionsDropdownContent.vue'
export { default as DesktopCardHeader } from './parts/DesktopCardHeader.vue'
export { default as DesktopCardFooter } from './parts/DesktopCardFooter.vue'

export { default as DesktopCardIp } from './parts/DesktopCardIp.vue'
export { default as DesktopCardNetworksOverlay } from './parts/DesktopCardNetworksOverlay.vue'
export { default as DesktopCardInfoOverlay } from './parts/DesktopCardInfoOverlay.vue'
export { default as DesktopCardBastionOverlay } from './parts/DesktopCardBastionOverlay.vue'
export { default as DesktopCardPreview } from './parts/DesktopCardPreview.vue'

// --- Card size variants ---

export const cardSizes = ['2xs', 'xs', 'sm', 'md', 'lg', 'xl'] as const
export type CardSize = (typeof cardSizes)[number]

export const CARD_SIZE_INJECTION_KEY = Symbol('cardSize') as InjectionKey<CardSize>

// --- Header icon buttons ---

// Highlighted state when this icon's overlay is the active one.
export const overlayIconButtonClass = (active: boolean) =>
  [
    'w-9! h-9! flex align-center justify-center p-0! backdrop-blur-[4px]',
    active ? 'bg-base-white/30 hover:bg-base-white/40' : 'bg-base-black/30 hover:bg-base-black/50'
  ].join(' ')

export const cardBaseVariants = cva('overflow-hidden p-0', {
  variants: {
    size: {
      '2xs': 'h-[150px] border-l-4 rounded-md',
      xs: 'h-[200px] border-l-6 rounded-lg',
      sm: 'h-[250px] border-l-8 rounded-lg',
      md: 'h-[280px] border-l-8 rounded-[10px]',
      lg: 'h-[310px] border-l-10 rounded-[10px]',
      xl: 'h-[370px] border-l-12 rounded-xl'
    },
    fill: {
      true: 'w-full',
      false: ''
    }
  },
  compoundVariants: [
    { fill: false, size: '2xs', class: 'w-[180px]' },
    { fill: false, size: 'xs', class: 'w-[240px]' },
    { fill: false, size: 'sm', class: 'w-[320px]' },
    { fill: false, size: 'md', class: 'w-[370px]' },
    { fill: false, size: 'lg', class: 'w-[426px]' },
    { fill: false, size: 'xl', class: 'w-[520px]' }
  ],
  defaultVariants: {
    size: 'lg',
    fill: false
  }
})

export const cardImageVariants = cva(
  'relative shrink-0 w-full bg-cover bg-center flex flex-col justify-end overflow-hidden',
  {
    variants: {
      size: {
        '2xs': 'h-20 pb-1',
        xs: 'h-28 pb-2',
        sm: 'h-40 pb-3',
        md: 'h-48 pb-3',
        lg: 'h-60 pb-4',
        xl: 'h-72 pb-5'
      }
    },
    defaultVariants: {
      size: 'lg'
    }
  }
)

export const cardGradientVariants = cva(
  'absolute bottom-0 left-0 right-0 bg-linear-to-t from-black/90 via-black/50 to-transparent z-0',
  {
    variants: {
      size: {
        '2xs': 'h-[60px]',
        xs: 'h-[90px]',
        sm: 'h-[120px]',
        md: 'h-[140px]',
        lg: 'h-[165px]',
        xl: 'h-[200px]'
      }
    },
    defaultVariants: {
      size: 'lg'
    }
  }
)

export const cardHeaderActionsVariants = cva('absolute flex items-center z-20', {
  variants: {
    size: {
      '2xs': 'top-1 right-1 gap-1',
      xs: 'top-1.5 right-1.5 gap-1.5',
      sm: 'top-2 right-2 gap-2',
      md: 'top-2.5 right-2.5 gap-[10px]',
      lg: 'top-3 right-3 gap-[14px]',
      xl: 'top-4 right-4 gap-4'
    }
  },
  defaultVariants: {
    size: 'lg'
  }
})

export const cardHeaderSlotVariants = cva('flex flex-col z-20 w-full overflow-hidden', {
  variants: {
    size: {
      '2xs': 'gap-0.5 px-1.5',
      xs: 'gap-0.5 px-2',
      sm: 'gap-0.5 px-2.5',
      md: 'gap-1 px-3',
      lg: 'gap-1 px-3',
      xl: 'gap-1.5 px-4'
    }
  },
  defaultVariants: {
    size: 'lg'
  }
})

export const cardFooterVariants = cva(
  'w-full bg-base-white flex-1 flex flex-row items-center justify-center mx-auto border-b border-r border-gray-warm-300',
  {
    variants: {
      size: {
        '2xs': 'gap-1 px-2 rounded-br-md',
        xs: 'gap-2 px-3 rounded-br-lg',
        sm: 'gap-3 px-3 rounded-br-lg',
        md: 'gap-3 px-4 rounded-br-[10px]',
        lg: 'gap-4 px-4 rounded-br-[10px]',
        xl: 'gap-5 px-5 rounded-br-xl'
      }
    },
    defaultVariants: {
      size: 'lg'
    }
  }
)

export const cardIconTriggerVariants = cva('absolute top-0 flex items-center justify-center', {
  variants: {
    size: {
      '2xs': 'w-[20px] h-5 left-0',
      xs: 'w-[30px] h-7 left-[-6px]',
      sm: 'w-[36px] h-9 left-[-8px]',
      md: 'w-[44px] h-10 left-[-8px]',
      lg: 'w-[50px] h-12 left-[-10px]',
      xl: 'w-[56px] h-14 left-[-12px]'
    }
  },
  defaultVariants: {
    size: 'lg'
  }
})

export const cardIpAreaVariants = cva('z-10 absolute top-0 flex items-center', {
  variants: {
    size: {
      '2xs': 'left-[16px] h-5 px-1',
      xs: 'left-[24px] h-7 px-2',
      sm: 'left-[30px] h-9 px-3',
      md: 'left-[36px] h-10 px-3',
      lg: 'left-[40px] h-12 px-4',
      xl: 'left-[48px] h-14 px-5'
    }
  },
  defaultVariants: {
    size: 'lg'
  }
})

export const cardNetworkVariants = cva('z-10', {
  variants: {
    size: {
      '2xs': 'px-1.5',
      xs: 'px-2',
      sm: 'px-2.5',
      md: 'px-3',
      lg: 'px-3',
      xl: 'px-4'
    }
  },
  defaultVariants: {
    size: 'lg'
  }
})

// Left padding to clear the colored type-identifier sidebar SVG that
// extends from the top-left corner over the image area. Matches the offset
// in `cardIpAreaVariants` so the overlay header doesn't collide with it.
export const cardOverlayPaddingVariants = cva('z-10', {
  variants: {
    size: {
      '2xs': 'pl-[20px] pr-1.5 pb-1',
      xs: 'pl-[28px] pr-2 pb-1',
      sm: 'pl-[34px] pr-2.5 pb-1.5',
      md: 'pl-[40px] pr-3 pb-2',
      lg: 'pl-[44px] pr-3 pb-2',
      xl: 'pl-[52px] pr-4 pb-2'
    }
  },
  defaultVariants: {
    size: 'lg'
  }
})

// --- Header sub-component variants ---

export const cardHeaderNameVariants = cva('font-bold text-start truncate text-base-white', {
  variants: {
    size: {
      '2xs': 'text-xs',
      xs: 'text-sm',
      sm: 'text-base',
      md: 'text-base',
      lg: 'text-lg',
      xl: 'text-xl'
    }
  },
  defaultVariants: {
    size: 'lg'
  }
})

export const cardHeaderDescriptionVariants = cva(
  'font-semibold text-start truncate text-base-white',
  {
    variants: {
      size: {
        '2xs': 'text-[9px]',
        xs: 'text-[10px]',
        sm: 'text-[11px]',
        md: 'text-xs',
        lg: 'text-xs',
        xl: 'text-sm'
      }
    },
    defaultVariants: {
      size: 'lg'
    }
  }
)

export const cardHeaderNotificationVariants = cva(
  'inline-flex items-center p-1.5 rounded-sm font-bold text-start text-base-white bg-[#131313]/40 max-w-full w-max backdrop-blur-[4px]',
  {
    variants: {
      size: {
        '2xs': 'gap-1 h-4 text-[8px]',
        xs: 'gap-1 h-5 text-[9px]',
        sm: 'gap-1.5 h-5 text-[10px]',
        md: 'gap-1.5 h-6 text-[11px]',
        lg: 'gap-1.5 h-6 text-[11px]',
        xl: 'gap-2 h-7 text-xs'
      }
    },
    defaultVariants: {
      size: 'lg'
    }
  }
)
