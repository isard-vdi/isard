<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Modal from './Modal.vue'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { CheckboxGroup } from '@/components/checkbox-group'
import type { CardItem } from '@/components/checkbox-group/card-item'
import { cn } from '@/lib/utils'
import stopGraceful from '@/assets/img/modal/stop-graceful.svg'
import stopForce from '@/assets/img/modal/stop-force.svg'

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

const liveCounts = computed(() => ({
  started: props.startedCount,
  shuttingDown: props.shuttingDownCount
}))
const frozenCounts = ref<{ started: number; shuttingDown: number } | null>(null)
watch(
  () => props.pending,
  (pending) => {
    frozenCounts.value = pending ? liveCounts.value : null
  }
)
const counts = computed(() => frozenCounts.value ?? liveCounts.value)

const forceOnly = computed(
  () => props.forceSupported && counts.value.started === 0 && counts.value.shuttingDown > 0
)

watch(
  () => props.open,
  (open) => {
    if (open) mode.value = forceOnly.value ? 'force' : 'graceful'
  }
)

watch(forceOnly, (only) => {
  if (only) mode.value = 'force'
})

// A forced stop also reaches the ones already shutting down, so the count has
// to follow the selected mode.
const affectedCount = computed(() =>
  mode.value === 'force' ? counts.value.started + counts.value.shuttingDown : counts.value.started
)

const nothingToStop = computed(() => affectedCount.value === 0)

const description = computed(() => {
  if (props.pending) return t('components.stop-all-desktops-modal.loading')
  if (nothingToStop.value) return t('components.stop-all-desktops-modal.nothing-to-stop')
  return forceOnly.value
    ? t('components.stop-all-desktops-modal.force-only.description', counts.value.shuttingDown)
    : t('components.stop-all-desktops-modal.description', affectedCount.value)
})

const skippedNote = computed(() =>
  !props.pending &&
  !nothingToStop.value &&
  mode.value === 'graceful' &&
  counts.value.shuttingDown > 0
    ? t('components.stop-all-desktops-modal.skipped', counts.value.shuttingDown)
    : ''
)

const modes = computed<CardItem[]>(() => [
  {
    value: 'graceful',
    icon: 'power-01',
    color: 'brand',
    image: stopGraceful,
    title: t('components.stop-all-desktops-modal.mode.graceful.title'),
    description: forceOnly.value
      ? t('components.stop-all-desktops-modal.mode.graceful.disabled')
      : t('components.stop-all-desktops-modal.mode.graceful.description'),
    disabled: forceOnly.value,
    class: 'flex-1 [&_img]:max-h-40'
  },
  {
    value: 'force',
    icon: 'lightning-01',
    color: 'error',
    image: stopForce,
    title: t('components.stop-all-desktops-modal.mode.force.title'),
    description: t('components.stop-all-desktops-modal.mode.force.description'),
    class: 'flex-1 [&_img]:max-h-40'
  }
])
</script>

<template>
  <Modal
    :open="props.open"
    size="3xl"
    class="pt-4"
    :title="t('components.stop-all-desktops-modal.title')"
    :description="description"
    @close="emit('close')"
  >
    <Alert v-if="props.error" variant="destructive" class="mb-4">
      <AlertDescription>{{ props.error }}</AlertDescription>
    </Alert>
    <p v-if="skippedNote" class="text-sm text-gray-warm-500 whitespace-pre-line">
      {{ skippedNote }}
    </p>
    <CheckboxGroup
      v-if="props.forceSupported"
      v-model="mode"
      class="mt-4 mb-2"
      :items="modes"
      kind="card"
      type="single"
      direction="flex-col md:flex-row"
    />
    <template #footer>
      <Button hierarchy="link-gray" @click="emit('close')">
        {{ t('components.stop-all-desktops-modal.cancel') }}
      </Button>
      <Button
        hierarchy="destructive"
        :icon="props.pending ? 'loading-02' : 'stop'"
        :icon-class="cn(props.pending && 'motion-safe:animate-[spin_2s_linear_infinite]')"
        :disabled="props.pending || nothingToStop"
        @click="emit('confirm', mode === 'force')"
      >
        {{
          mode === 'force'
            ? t('components.stop-all-desktops-modal.confirm.force')
            : t('components.stop-all-desktops-modal.confirm.graceful')
        }}
      </Button>
    </template>
  </Modal>
</template>
