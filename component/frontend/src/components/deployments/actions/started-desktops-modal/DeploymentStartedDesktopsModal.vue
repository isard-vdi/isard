<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { AlertModal } from '@/components/modal'
import { Icon } from '@/components/icon'
import { Button } from '@/components/ui/button'

interface Props {
  open?: boolean
  deploymentId: string
  startedCount: number
  /** Off where the stop buttons are already on screen: the deployment's own page. */
  showManageLink?: boolean
}

const props = withDefaults(defineProps<Props>(), { open: false, showManageLink: false })

const emit = defineEmits<{
  close: []
}>()

const { t } = useI18n()
</script>

<template>
  <AlertModal
    :open="props.open"
    level="warning"
    :title="t('components.deployments.started-desktops-modal.title', props.startedCount)"
    size="lg"
    @close="emit('close')"
  >
    <template #description>
      <p class="wrap-break-word">
        {{ t('components.deployments.started-desktops-modal.description') }}
      </p>
      <p v-if="props.showManageLink" class="mt-3 flex items-start gap-2 text-sm text-gray-warm-600">
        <Icon name="info-circle" size="sm" stroke-color="gray-warm-500" class="mt-0.5 shrink-0" />
        {{ t('components.deployments.started-desktops-modal.manage-hint') }}
      </p>
    </template>
    <template #footer>
      <Button hierarchy="link-gray" @click="emit('close')">
        {{ t('components.deployments.started-desktops-modal.close') }}
      </Button>
      <Button
        v-if="props.showManageLink"
        hierarchy="secondary-gray"
        :as="RouterLink"
        :to="{ name: 'deployment', params: { deploymentId: props.deploymentId } }"
      >
        {{ t('components.deployments.started-desktops-modal.manage') }}
      </Button>
    </template>
  </AlertModal>
</template>
