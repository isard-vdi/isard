<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMutation } from '@tanstack/vue-query'

import { AlertModal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { useMessageModalStore } from '@/stores/message-modal'
import { extendDesktopTimeoutApiV4ItemDesktopDesktopIdExtendTimeoutPutMutation } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

const { t, te } = useI18n()
const store = useMessageModalStore()

const description = computed(() => {
  if (!store.msgCode) return ''
  const key = `components.message-modal.messages.${store.msgCode}`
  return te(key) ? t(key, store.params as Record<string, unknown>) : ''
})

const { mutate: extendTimeout, isPending: isExtending } = useMutation({
  ...extendDesktopTimeoutApiV4ItemDesktopDesktopIdExtendTimeoutPutMutation(),
  onSuccess: () => store.hide()
})

const onExtend = () => {
  if (!store.desktopId) return
  extendTimeout({ path: { desktop_id: store.desktopId } })
}

const onUpdateOpen = (value: boolean) => {
  if (!value) store.hide()
}
</script>

<template>
  <AlertModal
    :open="store.open"
    size="md"
    :level="store.level"
    :title="t('components.message-modal.title')"
    :description="description"
    :loading="isExtending"
    :close-on-backdrop-click="!isExtending"
    :show-close-button="!isExtending"
    @update:open="onUpdateOpen"
  >
    <template v-if="store.canExtend" #footer>
      <Button size="lg" hierarchy="primary" :disabled="isExtending" @click="onExtend">
        <Spinner v-if="isExtending" size="sm" class="mr-1" />
        {{ t('components.message-modal.extend-time', { minutes: store.extendTime }) }}
      </Button>
    </template>
  </AlertModal>
</template>
