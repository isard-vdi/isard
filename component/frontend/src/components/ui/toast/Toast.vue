<script setup lang="ts">
import { computed } from 'vue'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/icon'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import type { FeaturedIconOutlineVariants } from '@/components/icon/featured-outline'
import { Spinner } from '@/components/ui/spinner'
import { cn } from '@/lib/utils'
import { toastVariants } from '.'
import type { ToastAction, ToastEntry, ToastId } from './state'

const props = withDefaults(
  defineProps<{
    toast: ToastEntry
    /** Global close-button default supplied by `<Toaster>`. */
    closeButton?: boolean
  }>(),
  {
    closeButton: false
  }
)

const emit = defineEmits<{
  dismiss: [id: ToastId]
}>()

// Map each toast type to a FeaturedIconOutline color (no `info` color exists →
// `brand`, matching the recycle-bin info-alert precedent).
const COLOR_BY_TYPE: Record<string, FeaturedIconOutlineVariants['color']> = {
  success: 'success',
  info: 'brand',
  warning: 'warning',
  error: 'error',
  default: 'gray',
  loading: 'gray'
}

const isCustom = computed(() => Boolean(props.toast.component))
const isLoading = computed(() => props.toast.type === 'loading')
const showClose = computed(() => props.toast.closeButton ?? props.closeButton)
const iconColor = computed(() => COLOR_BY_TYPE[props.toast.type] ?? 'gray')
const ariaRole = computed(() => (props.toast.type === 'error' ? 'alert' : 'status'))

function handleAction(action: ToastAction, event: MouseEvent) {
  action.onClick(event)
  if (!action.keepOpen) emit('dismiss', props.toast.id)
}
</script>

<template>
  <Alert
    :role="ariaRole"
    aria-atomic="true"
    :class="
      cn(
        'pointer-events-auto relative w-full max-w-[356px]',
        // Drop Alert's 10px icon margin; center the badge/spinner only on single-line toasts.
        '[&>.icon]:m-0',
        '[&>svg]:m-0',
        !toast.description && !toast.actions.length
          ? '[&>.icon]:top-1/2 [&>.icon]:-translate-y-1/2 [&>svg]:top-1/2 [&>svg]:-translate-y-1/2'
          : '',
        toastVariants({ type: toast.type }),
        toast.class
      )
    "
  >
    <!-- Type indicator: leading <svg>/.icon so Alert's positioning rules apply. -->
    <Spinner v-if="isLoading" size="sm" />
    <FeaturedIconOutline
      v-else-if="toast.icon"
      :name="toast.icon"
      :color="iconColor"
      kind="outline"
      size="md"
    />

    <div :class="cn('flex flex-col gap-1', showClose && 'pr-6')">
      <component :is="toast.component" v-if="isCustom" v-bind="toast.componentProps" />
      <template v-else>
        <AlertTitle v-if="toast.message">{{ toast.message }}</AlertTitle>
        <AlertDescription v-if="toast.description" class="text-gray-warm-600">
          {{ toast.description }}
        </AlertDescription>
      </template>

      <div v-if="toast.actions.length" class="mt-2 flex flex-wrap gap-2">
        <Button
          v-for="(action, index) in toast.actions"
          :key="index"
          :hierarchy="action.hierarchy ?? 'link-color'"
          :size="action.size ?? 'sm'"
          @click="(event: MouseEvent) => handleAction(action, event)"
        >
          {{ action.label }}
        </Button>
      </div>
    </div>
    <Button
      v-if="showClose"
      hierarchy="link-color"
      class="absolute top-1 right-1 cursor-pointer"
      aria-label="Close notification"
      @click="emit('dismiss', toast.id)"
    >
      <Icon name="x" stroke-color="secondary-2-500" size="sm" />
    </Button>
  </Alert>
</template>
