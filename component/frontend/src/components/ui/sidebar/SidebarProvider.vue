<script setup lang="ts">
import type { HTMLAttributes, Ref } from 'vue'
import { useEventListener, useMediaQuery, useVModel } from '@vueuse/core'
import { useCookies } from '@vueuse/integrations/useCookies'
import { TooltipProvider } from 'reka-ui'
import { computed, ref, watch } from 'vue'
import { cn } from '@/lib/utils'
import {
  provideSidebarContext,
  SIDEBAR_COOKIE_MAX_AGE,
  SIDEBAR_COOKIE_NAME,
  SIDEBAR_KEYBOARD_SHORTCUT,
  SIDEBAR_WIDTH,
  SIDEBAR_WIDTH_ICON
} from './utils'

const props = withDefaults(
  defineProps<{
    defaultOpen?: boolean
    open?: boolean
    class?: HTMLAttributes['class']
  }>(),
  {
    open: undefined
  }
)

const emits = defineEmits<{
  'update:open': [open: boolean]
}>()

const cookies = useCookies([SIDEBAR_COOKIE_NAME])
const isMobile = useMediaQuery('(max-width: 768px)')
const openMobile = ref(false)

// Compute the default open state from cookie if no prop is provided
const defaultOpenValue = (() => {
  if (props.defaultOpen !== undefined) {
    return props.defaultOpen
  }
  const cookieValue = cookies.get(SIDEBAR_COOKIE_NAME)
  // useCookies auto-parses "true"/"false" to boolean, so check both types
  if (cookieValue === null || cookieValue === undefined) {
    return true
  }
  return cookieValue === true || cookieValue === 'true'
})()

const open = useVModel(props, 'open', emits, {
  defaultValue: defaultOpenValue,
  passive: (props.open === undefined) as false
}) as Ref<boolean>

// Watch open state and update cookie
watch(open, (newValue) => {
  cookies.set(SIDEBAR_COOKIE_NAME, String(newValue), {
    path: '/',
    maxAge: SIDEBAR_COOKIE_MAX_AGE
  })
})

function setOpen(value: boolean) {
  open.value = value
}

function setOpenMobile(value: boolean) {
  openMobile.value = value
}

// Helper to toggle the sidebar.
function toggleSidebar() {
  return isMobile.value ? setOpenMobile(!openMobile.value) : setOpen(!open.value)
}

useEventListener('keydown', (event: KeyboardEvent) => {
  if (event.key === SIDEBAR_KEYBOARD_SHORTCUT && (event.metaKey || event.ctrlKey)) {
    event.preventDefault()
    toggleSidebar()
  }
})

// We add a state so that we can do data-state="expanded" or "collapsed".
// This makes it easier to style the sidebar with Tailwind classes.
const state = computed(() => (open.value ? 'expanded' : 'collapsed'))

provideSidebarContext({
  state,
  open,
  setOpen,
  isMobile,
  openMobile,
  setOpenMobile,
  toggleSidebar
})
</script>

<template>
  <TooltipProvider :delay-duration="0">
    <div
      :style="{
        '--sidebar-width': SIDEBAR_WIDTH,
        '--sidebar-width-icon': SIDEBAR_WIDTH_ICON
      }"
      :class="
        cn(
          'group/sidebar-wrapper flex min-h-svh w-full has-[[data-variant=inset]]:bg-sidebar',
          props.class
        )
      "
      v-bind="$attrs"
    >
      <slot />
    </div>
  </TooltipProvider>
</template>
