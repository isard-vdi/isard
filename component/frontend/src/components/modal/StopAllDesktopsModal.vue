<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AlertModal from './AlertModal.vue'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { CheckboxGroup } from '@/components/checkbox-group'
import type { FeaturedIconItem } from '@/components/checkbox-group/featured-icon'
import { cn } from '@/lib/utils'

interface Props {
  open?: boolean
  /** Desktops in Started: the only ones a graceful stop reaches. */
  startedCount?: number
  /** Desktops already shutting down: only a forced stop reaches those. */
  shuttingDownCount?: number
  /** Stop endpoints that take no `force` hide the mode picker altogether. */
  forceSupported?: boolean
  pending?: boolean
  error?: string
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  startedCount: 0,
  shuttingDownCount: 0,
  forceSupported: true,
  pending: false,
  error: ''
})

const emit = defineEmits<{
  close: []
  confirm: [force: boolean]
}>()

const { t } = useI18n()

const mode = ref('graceful')
const counts = ref({ started: 0, shuttingDown: 0 })

const forceOnly = computed(
  () => props.forceSupported && counts.value.started === 0 && counts.value.shuttingDown > 0
)

watch(
  () => props.open,
  (open) => {
    if (!open) return
    counts.value = { started: props.startedCount, shuttingDown: props.shuttingDownCount }
    mode.value = forceOnly.value ? 'force' : 'graceful'
  },
  { immediate: true }
)

// A forced stop also reaches the ones already shutting down, so the count has
// to follow the selected mode.
const affectedCount = computed(() =>
  mode.value === 'force' ? counts.value.started + counts.value.shuttingDown : counts.value.started
)

const description = computed(() => {
  if (props.pending) return t('components.stop-all-desktops-modal.loading')
  return forceOnly.value
    ? t('components.stop-all-desktops-modal.force-only.description', counts.value.shuttingDown)
    : t('components.stop-all-desktops-modal.description', affectedCount.value)
})

const skippedNote = computed(() =>
  !props.pending && mode.value === 'graceful' && counts.value.shuttingDown > 0
    ? t('components.stop-all-desktops-modal.skipped', counts.value.shuttingDown)
    : ''
)

const modes = computed<FeaturedIconItem[]>(() => [
  {
    value: 'graceful',
    icon: 'power-01',
    color: 'brand',
    title: t('components.stop-all-desktops-modal.mode.graceful.title'),
    description: forceOnly.value
      ? t('components.stop-all-desktops-modal.mode.graceful.disabled')
      : t('components.stop-all-desktops-modal.mode.graceful.description'),
    disabled: forceOnly.value
  },
  {
    value: 'force',
    icon: 'lightning-01',
    color: 'error',
    title: t('components.stop-all-desktops-modal.mode.force.title'),
    description: t('components.stop-all-desktops-modal.mode.force.description')
  }
])
</script>

<template>
  <AlertModal
    :open="props.open"
    level="warning"
    size="xl"
    :title="t('components.stop-all-desktops-modal.title')"
    @close="emit('close')"
  >
    <template #description>
      <Alert v-if="props.error" variant="destructive" class="mb-4">
        <AlertDescription>{{ props.error }}</AlertDescription>
      </Alert>
      <p class="whitespace-pre-line">{{ description }}</p>
      <p v-if="skippedNote" class="mt-1 text-sm text-gray-warm-500 whitespace-pre-line">
        {{ skippedNote }}
      </p>
      <CheckboxGroup
        v-if="props.forceSupported"
        v-model="mode"
        class="mt-4 [&>*]:flex-1 [&_p:first-child]:font-bold"
        :items="modes"
        kind="featured-icon"
        type="single"
        check-type="radio"
        direction="flex-row"
      />
    </template>
    <template #footer>
      <Button hierarchy="link-gray" @click="emit('close')">
        {{ t('components.stop-all-desktops-modal.cancel') }}
      </Button>
      <Button
        hierarchy="destructive"
        :icon="props.pending ? 'loading-02' : 'stop'"
        :icon-class="cn(props.pending && 'motion-safe:animate-[spin_2s_linear_infinite]')"
        :disabled="props.pending"
        @click="emit('confirm', mode === 'force')"
      >
        {{
          forceOnly
            ? t('components.stop-all-desktops-modal.force-only.confirm')
            : t('components.stop-all-desktops-modal.confirm')
        }}
      </Button>
    </template>
  </AlertModal>
</template>
