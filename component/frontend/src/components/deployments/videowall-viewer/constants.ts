export type ViewerMode = 'view' | 'control'
export type ViewerLayout = 'single' | 'mosaic'
export type MosaicDensity = 'lg' | 'md' | 'sm'
export interface ViewerNotice {
  kind: ViewerMode | 'pinned'
  key: number
}

// Pins always stream, seen or not, so nothing a user does is missed.
export const MAX_PINNED = 10

export const MOSAIC_TILE_MIN_WIDTH: Record<MosaicDensity, number> = { lg: 480, md: 320, sm: 220 }

export const BAR_BUTTON =
  'flex size-10 shrink-0 cursor-pointer items-center justify-center rounded-md outline-hidden hover:bg-gray-warm-100 focus-visible:ring-3 focus-visible:ring-gray disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent'

export const TOGGLE_GROUP = 'shrink-0 rounded-md border border-gray-warm-200 bg-gray-warm-100 p-0.5'

// The tooltip trigger overwrites data-state with its own, so the pressed one goes by aria-pressed.
export const TOGGLE_ITEM =
  'h-8 cursor-pointer gap-1.5 px-2.5 text-gray-warm-600 hover:bg-gray-warm-200 hover:text-gray-warm-900 aria-pressed:cursor-default focus-visible:ring-3 focus-visible:ring-gray'

export const PRESSED_NEUTRAL =
  'aria-pressed:bg-gray-warm-600 aria-pressed:text-base-white aria-pressed:hover:bg-gray-warm-600 aria-pressed:hover:text-base-white'

// Amber means control: the pressed button, the notice and the flash.
export const PRESSED_AMBER =
  'aria-pressed:bg-warning-500 aria-pressed:text-gray-warm-900 aria-pressed:hover:bg-warning-500 aria-pressed:hover:text-gray-warm-900'

// Truncate only the texts: the avatar keeps its size and its initials whole.
export const AVATAR_LABEL_TRUNCATE =
  'min-w-0 [&>div:first-child]:shrink-0 [&>div:last-child]:min-w-0 [&>div:last-child>span]:truncate'
