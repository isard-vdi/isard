<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'

import { Modal } from '@/components/modal'
import { Switch } from '@/components/ui/switch'
import { Button } from '@/components/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { InputField } from '@/components/input-field'
import CopyIcon from '@/components/icon/CopyIcon.vue'

import dotGrid from '@/assets/img/modal/dot-grid.svg?component'
import directViewerImg from '@/assets/img/modal/direct-viewer.svg'

import {
  getShareLinkOptions,
  getShareLinkQueryKey,
  updateShareLinkMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

const { t } = useI18n()

export interface Props {
  open?: boolean
  desktopId: string | null
}

const props = withDefaults(defineProps<Props>(), {
  open: false
})

const emit = defineEmits<{
  close: []
}>()

const queryClient = useQueryClient()

const shareLinkQueryKey = computed(() =>
  getShareLinkQueryKey({
    path: { desktop_id: props.desktopId ?? '' }
  })
)

const { data: shareLinkData } = useQuery({
  ...getShareLinkOptions({
    path: { desktop_id: props.desktopId ?? '' }
  }),
  queryKey: shareLinkQueryKey,
  enabled: computed(() => props.open && props.desktopId !== null)
})

const isEnabled = computed(() => !!shareLinkData.value?.link)

const switchValue = computed(() => (showDisableAlert.value ? false : isEnabled.value))

const url = computed(() => {
  if (!shareLinkData.value?.link) return null
  return `${location.protocol}//${location.host}/vw/${shareLinkData.value.link}`
})

const mutation = useMutation({
  ...updateShareLinkMutation(),
  onSuccess() {
    queryClient.invalidateQueries({
      queryKey: shareLinkQueryKey.value
    })
  }
})

const showDisableAlert = ref(false)

const handleSwitchToggle = (newValue: boolean) => {
  if (!newValue && isEnabled.value) {
    showDisableAlert.value = true
    return
  }

  if (newValue && showDisableAlert.value) {
    showDisableAlert.value = false
    return
  }

  if (newValue && !isEnabled.value) {
    mutation.mutate({
      path: { desktop_id: props.desktopId! },
      body: { enabled: true }
    })
  }
}

const confirmDisable = () => {
  showDisableAlert.value = false
  mutation.mutate({
    path: { desktop_id: props.desktopId! },
    body: { enabled: false }
  })
}

watch(
  () => props.open,
  (open) => {
    if (!open) {
      showDisableAlert.value = false
    }
  }
)
</script>

<template>
  <Modal
    :title="t('components.desktops.direct-viewer-modal.title')"
    :open="props.open"
    class="max-w-96"
    @close="emit('close')"
  >
    <template #image>
      <div
        class="relative w-96 overflow-hidden flex items-center justify-center pointer-events-none select-none"
      >
        <component
          :is="dotGrid"
          class="absolute h-full opacity-30 max-w-94 mt-1"
          :style="{
            fill: 'var(--gray-warm-300)',
            maskImage: 'linear-gradient(to bottom, black 10%, transparent 100%)'
          }"
          aria-hidden="true"
        />
        <img :src="directViewerImg" class="relative z-20 w-full max-h-56 mt-5" />
      </div>
    </template>

    <div class="flex flex-col gap-5 pb-5">
      <div class="flex items-center gap-3">
        <Switch
          :model-value="switchValue"
          :disabled="showDisableAlert"
          @update:model-value="handleSwitchToggle"
        />
        <span class="text-sm text-gray-warm-700">
          {{ t('components.desktops.direct-viewer-modal.enable-access') }}
        </span>
      </div>

      <div class="flex flex-col gap-3">
        <template v-if="showDisableAlert">
          <Alert variant="destructive" class="flex flex-col gap-2">
            <AlertTitle>
              {{ t('components.desktops.direct-viewer-modal.disable-confirmation.title') }}
            </AlertTitle>
            <AlertDescription>
              {{ t('components.desktops.direct-viewer-modal.disable-confirmation.description') }}
            </AlertDescription>
            <div class="flex justify-end gap-2 mt-2">
              <Button hierarchy="link-color" @click="showDisableAlert = false">
                {{ t('components.desktops.direct-viewer-modal.disable-confirmation.cancel') }}
              </Button>
              <Button hierarchy="primary" @click="confirmDisable">
                {{ t('components.desktops.direct-viewer-modal.disable-confirmation.confirm') }}
              </Button>
            </div>
          </Alert>
        </template>
        <template v-else-if="isEnabled && url">
          <div class="flex items-center gap-2">
            <InputField :model-value="url" readonly class="flex-1" />
            <CopyIcon :value="url" size="md" stroke-color="brand-700" />
          </div>
        </template>
      </div>
    </div>
  </Modal>
</template>
