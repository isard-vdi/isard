<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { AlertModal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import { useDeploymentVisibility } from '@/composables/useDeploymentVisibility'

interface Props {
  open?: boolean
  deploymentId: string
  deploymentName?: string | null
  /** Explicit direction: both "show all" and "hide all" confirm. */
  action: 'show' | 'hide'
  onSuccess?: () => void
}

const props = withDefaults(defineProps<Props>(), { open: false })

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'close'): void
}>()

const { t } = useI18n()

const hiding = computed(() => props.action === 'hide')

const handleClose = () => {
  emit('update:open', false)
  emit('close')
}

const { mutate: setVisibility, isPending } = useDeploymentVisibility(() => props.deploymentId)

// No selectors: this is the master switch, so it covers every desktop.
const apply = (stopStartedDomains: boolean) => {
  if (!props.deploymentId) return
  setVisibility(
    {
      path: { deployment_id: props.deploymentId },
      body: { visible: !hiding.value, stop_started_domains: stopStartedDomains }
    },
    {
      onSuccess: () => {
        handleClose()
        props.onSuccess?.()
      }
    }
  )
}
</script>

<template>
  <AlertModal
    :open="props.open"
    :level="hiding ? 'warning' : 'info'"
    size="lg"
    :title="
      hiding
        ? t('views.deployment.toggle-lab-visibility.title-invisible')
        : t('views.deployment.toggle-lab-visibility.title-visible')
    "
    :description="
      hiding
        ? t('views.deployment.toggle-lab-visibility.description-invisible')
        : t('views.deployment.toggle-lab-visibility.description-visible')
    "
    @close="handleClose"
  >
    <template #footer>
      <Button hierarchy="link-gray" :disabled="isPending" @click="handleClose">
        {{ t('views.deployment.toggle-lab-visibility.cancel') }}
      </Button>

      <template v-if="hiding">
        <Button hierarchy="secondary-gray" :disabled="isPending" @click="apply(false)">
          {{ t('views.deployment.toggle-lab-visibility.only-hide') }}
        </Button>
        <Button hierarchy="destructive" :disabled="isPending" @click="apply(true)">
          {{ t('views.deployment.toggle-lab-visibility.hide-and-stop') }}
        </Button>
      </template>

      <Button v-else hierarchy="primary" :disabled="isPending" @click="apply(false)">
        {{ t('views.deployment.toggle-lab-visibility.confirm') }}
      </Button>
    </template>
  </AlertModal>
</template>
