<script setup lang="ts">
import { computed, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMutation } from '@tanstack/vue-query'

import { AlertModal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { toast } from '@/components/ui/toast'
import { describeApiError } from '@/lib/api-errors'
import { formatAsTime } from '@/lib/booking/date-utils'
import { clearDesktopTimeout, desktopTimeout } from '@/lib/desktop-timeout'
import { extendDesktopTimeoutMutation } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

const { t, te, d } = useI18n()

const description = computed(() => {
  const warning = desktopTimeout.value
  if (!warning) return ''
  return t('components.desktop-timeout-modal.description', {
    name: warning.name,
    date: d(warning.stopsAt, { timeStyle: 'short' })
  })
})

const extendMinutes = computed(() => desktopTimeout.value?.extendMinutes ?? null)

const { mutate: extendTimeout, isPending: isExtending } = useMutation({
  ...extendDesktopTimeoutMutation(),
  onSuccess: () => clearDesktopTimeout(),
  onError: (error) => toast.error(describeApiError(error, { t, te }, 'extend-desktop'))
})

const onExtend = () => {
  const desktopId = desktopTimeout.value?.desktopId
  if (desktopId) extendTimeout({ path: { desktop_id: desktopId } })
}

const onUpdateOpen = (value: boolean) => {
  if (!value) clearDesktopTimeout()
}

onUnmounted(clearDesktopTimeout)
</script>

<template>
  <AlertModal
    :open="desktopTimeout !== null"
    size="md"
    :level="desktopTimeout?.level ?? 'warning'"
    :title="t('components.desktop-timeout-modal.title')"
    :description="description"
    :close-on-backdrop-click="!isExtending"
    :show-close-button="!isExtending"
    @update:open="onUpdateOpen"
  >
    <template v-if="extendMinutes !== null" #footer>
      <Button size="lg" hierarchy="primary" :disabled="isExtending" @click="onExtend">
        <Spinner v-if="isExtending" size="sm" class="mr-1" />
        {{ t('components.desktop-timeout-modal.extend-time', { minutes: extendMinutes }) }}
      </Button>
    </template>
  </AlertModal>
</template>
