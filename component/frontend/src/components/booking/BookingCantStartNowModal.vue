<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/modal'

interface Props {
  open: boolean
  data: {
    id: string
    name: string
    currentGpu: string
    showChangeAndStart: boolean
  } | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  close: []
  changeAndStart: [payload: { id: string; name: string; currentGpu: string }]
  bookDesktop: [desktopId: string]
}>()

const { t } = useI18n()
</script>

<template>
  <Modal
    :open="props.open"
    class="pt-4 min-w-120"
    :title="
      t('components.desktop-gpu-unavailable-modal.title', {
        'current-gpu': props.data?.currentGpu,
        name: props.data?.name
      })
    "
    :description="t('components.desktop-gpu-unavailable-modal.description')"
    @close="emit('close')"
  >
    <div class="flex flex-col gap-4 mt-4">
      <Alert
        v-if="props.data?.showChangeAndStart"
        class="flex flex-row gap-4 items-center justify-between"
      >
        <div class="flex flex-col gap-2">
          <AlertTitle>{{
            t('components.desktop-gpu-unavailable-modal.change-and-start.title', {
              gpu: props.data?.currentGpu
            })
          }}</AlertTitle>
          <AlertDescription>{{
            t('components.desktop-gpu-unavailable-modal.change-and-start.subtitle')
          }}</AlertDescription>
        </div>
        <Button
          icon="switch-horizontal-01"
          @click="
            () => {
              if (!props.data) return
              emit('changeAndStart', {
                id: props.data.id,
                name: props.data.name,
                currentGpu: props.data.currentGpu
              })
            }
          "
          >{{
            t('components.desktop-gpu-unavailable-modal.change-and-start.action-button')
          }}</Button
        >
      </Alert>

      <Alert class="flex flex-row gap-4 items-center justify-between">
        <div class="flex flex-col gap-2">
          <AlertTitle>{{
            t('components.desktop-gpu-unavailable-modal.book.title', {
              gpu: props.data?.currentGpu
            })
          }}</AlertTitle>
          <AlertDescription>{{
            t('components.desktop-gpu-unavailable-modal.book.subtitle')
          }}</AlertDescription>
        </div>
        <Button
          icon="calendar-plus-02"
          @click="
            () => {
              if (props.data) emit('bookDesktop', props.data.id)
            }
          "
          >{{ t('components.desktop-gpu-unavailable-modal.book.action-button') }}</Button
        >
      </Alert>
    </div>
  </Modal>
</template>
