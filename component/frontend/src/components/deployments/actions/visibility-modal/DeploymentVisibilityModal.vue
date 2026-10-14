<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { AlertModal } from '@/components/modal'
import { Button } from '@/components/ui/button'

interface Props {
  open?: boolean
  /** Explicit direction: both "show" and "hide" can confirm. */
  action: 'show' | 'hide'
  /** Names the scope being changed — the caller knows it, the modal does not. */
  title: string
  /** Started desktops inside that scope. */
  runningCount?: number
}

const props = withDefaults(defineProps<Props>(), { open: false, runningCount: 0 })

const emit = defineEmits<{
  'update:open': [value: boolean]
  close: []
  confirm: [stopStartedDomains: boolean]
}>()

const { t } = useI18n()

const hiding = computed(() => props.action === 'hide')

/** Hiding a stopped desktop interrupts nobody, so only a running one asks. */
const offersStop = computed(() => hiding.value && props.runningCount > 0)

const description = computed(() => {
  const base = t(
    hiding.value
      ? 'views.deployment.visibility.confirm.description-hide'
      : 'views.deployment.visibility.confirm.description-show'
  )
  if (!offersStop.value) return base
  return `${base}\n\n${t('views.deployment.visibility.confirm.running', props.runningCount)}`
})

const handleClose = () => {
  emit('update:open', false)
  emit('close')
}
</script>

<template>
  <AlertModal
    :open="props.open"
    :level="hiding ? 'warning' : 'info'"
    :size="offersStop ? 'lg' : 'md'"
    :title="props.title"
    :description="description"
    @close="handleClose"
  >
    <template #footer>
      <Button hierarchy="link-gray" @click="handleClose">
        {{ t('views.deployment.visibility.confirm.cancel') }}
      </Button>

      <template v-if="offersStop">
        <Button hierarchy="secondary-gray" @click="emit('confirm', false)">
          {{ t('views.deployment.visibility.confirm.only-hide') }}
        </Button>
        <Button hierarchy="destructive" @click="emit('confirm', true)">
          {{ t('views.deployment.visibility.confirm.hide-and-stop') }}
        </Button>
      </template>

      <Button
        v-else
        :hierarchy="hiding ? 'destructive' : 'primary'"
        @click="emit('confirm', false)"
      >
        {{
          hiding
            ? t('views.deployment.visibility.confirm.hide')
            : t('views.deployment.visibility.confirm.show')
        }}
      </Button>
    </template>
  </AlertModal>
</template>
