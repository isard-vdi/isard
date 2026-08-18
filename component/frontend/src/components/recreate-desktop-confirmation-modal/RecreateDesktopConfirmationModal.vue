<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { useMutation } from '@tanstack/vue-query'

import { recreateDesktopMutation } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import { AlertModal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/icon'

const { t } = useI18n()

interface Props {
  open?: boolean
  desktop?: {
    id: string
    name: string
  } | null
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  desktop: null
})

const emit = defineEmits<{
  close: []
}>()

const {
  mutate: recreateDesktop,
  mutateAsync: recreateDesktopAsync,
  isPending: recreateDesktopIsPending,
  isError: recreateDesktopIsError,
  error: recreateDesktopError
} = useMutation({
  ...recreateDesktopMutation(),
  onSuccess: () => {
    emit('close')
  }
})
</script>

<template>
  <!-- Recreate modal -->
  <AlertModal
    :open="props.open"
    level="warning"
    size="lg"
    :title="
      t('components.recreate-desktop-confirmation-modal.title', {
        name: props.desktop?.name
      })
    "
    :description="t('components.recreate-desktop-confirmation-modal.description')"
    @close="emit('close')"
  >
    <template #footer>
      <Button hierarchy="link-gray" @click="emit('close')">{{
        t('components.recreate-desktop-confirmation-modal.cancel')
      }}</Button>

      <Button
        hierarchy="destructive"
        :disabled="recreateDesktopIsPending"
        @click="recreateDesktop({ path: { desktop_id: props.desktop?.id } })"
      >
        <Icon
          v-if="recreateDesktopIsPending"
          class="motion-safe:animate-[spin_2s_linear_infinite]"
          name="loading-02"
          stroke-color="currentColor"
        />
        {{ t('components.recreate-desktop-confirmation-modal.confirm') }}
      </Button>
    </template>
  </AlertModal>
</template>
