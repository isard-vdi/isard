<script setup lang="ts">
import { type RouteLocationRaw } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Button } from '@/components/ui/button'
import { AlertModal } from '@/components/modal'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useWindowScroll } from '@vueuse/core'
import { useUnsavedChangesGuard } from '@/composables/useUnsavedChangesGuard'
import { cn } from '@/lib/utils'

export interface FormHeaderTooltip {
  title: string
  description?: string
}

interface Props {
  cancelTo: RouteLocationRaw
  cancelLabel?: string
  confirmCancel?: boolean
  showPrevious?: boolean
  previousLabel?: string
  nextLabel?: string
  nextDisabled?: boolean
  nextPending?: boolean
  nextTooltip?: FormHeaderTooltip
}

const props = withDefaults(defineProps<Props>(), {
  cancelLabel: undefined,
  confirmCancel: false,
  showPrevious: false,
  previousLabel: undefined,
  nextLabel: undefined,
  nextDisabled: false,
  nextPending: false,
  nextTooltip: undefined
})

const emit = defineEmits<{
  previous: []
  next: []
}>()

const { t } = useI18n()

// The same confirmation whatever the exit is: this button, a sidebar link,
// the browser back button or a reload.
const { showDiscardModal, requestLeave, confirmDiscard, cancelDiscard, allowLeave } =
  useUnsavedChangesGuard(() => props.confirmCancel)

const { y: windowScrollY } = useWindowScroll()

const handleCancel = () => requestLeave(props.cancelTo)

/** Views call this before navigating away on a successful submit. */
defineExpose({ allowLeave })
</script>

<template>
  <!-- Sticky under the page header, so the step controls stay reachable while the form scrolls -->
  <header
    data-sticky-header
    :class="
      cn(
        'sticky top-16 z-40 -mx-[var(--page-gutter,1.5rem)] -mt-8 mb-6 px-[var(--page-gutter,1.5rem)] py-5 bg-base-background',
        // Masks the sliver between the page header and this one, so content cannot show through
        'before:absolute before:inset-x-0 before:bottom-full before:h-8 before:bg-base-background',
        windowScrollY > 0 && 'shadow-md'
      )
    "
  >
    <div
      class="flex flex-col md:flex-row items-start md:items-center max-w-480 w-full mx-auto gap-4"
    >
      <div class="flex flex-col gap-1 w-full">
        <Button
          hierarchy="link-destructive"
          icon="x-close"
          class="self-start p-0"
          @click="handleCancel"
        >
          {{ cancelLabel ?? t('components.form-header.cancel-creation') }}
        </Button>
      </div>

      <slot name="stepper" />

      <div class="flex flex-row items-center justify-end gap-4 w-full">
        <Button
          v-if="showPrevious"
          hierarchy="secondary-gray"
          icon="arrow-left"
          @click="emit('previous')"
        >
          {{ previousLabel ?? t('components.form-header.previous') }}
        </Button>

        <slot name="next">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger as-child>
                <!-- Wrapper: a disabled button emits no pointer events -->
                <span class="inline-flex">
                  <Button
                    class="min-w-32"
                    :disabled="nextDisabled || nextPending"
                    :icon="nextPending ? 'loading-02' : ''"
                    icon-class="motion-safe:animate-[spin_2s_linear_infinite]"
                    @click="emit('next')"
                  >
                    {{ nextLabel ?? t('components.form-header.next') }}
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent
                v-if="nextTooltip"
                :title="nextTooltip.title"
                :subtitle="nextTooltip.description"
                side="top"
              />
            </Tooltip>
          </TooltipProvider>
        </slot>
      </div>
    </div>
  </header>

  <AlertModal
    :open="showDiscardModal"
    level="warning"
    :title="t('components.form-header.discard-modal.title')"
    :description="t('components.form-header.discard-modal.description')"
    @close="cancelDiscard"
  >
    <template #footer>
      <Button hierarchy="secondary-gray" @click="cancelDiscard">
        {{ t('components.form-header.discard-modal.cancel') }}
      </Button>
      <Button hierarchy="destructive" @click="confirmDiscard">
        {{ t('components.form-header.discard-modal.confirm') }}
      </Button>
    </template>
  </AlertModal>
</template>
