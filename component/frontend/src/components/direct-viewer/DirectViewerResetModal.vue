<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useMutation } from '@tanstack/vue-query'
import { resetDesktopApiV4ItemDesktopTokenTokenResetDesktopPutMutation } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

interface Props {
  open?: boolean
  token: string
}

const props = withDefaults(defineProps<Props>(), { open: false })
const emit = defineEmits<{ close: [] }>()

const { t } = useI18n()

const reset = useMutation(resetDesktopApiV4ItemDesktopTokenTokenResetDesktopPutMutation())

function handleReset() {
  reset.mutate(
    { path: { token: props.token } },
    {
      onSettled: () => emit('close')
    }
  )
}
</script>

<template>
  <Dialog :open="props.open" @update:open="(v) => !v && emit('close')">
    <DialogContent
      class="bg-base-background shadow-md max-h-[90vh] flex flex-col p-0 w-[95vw] max-w-2xl"
    >
      <DialogHeader class="bg-error-600 text-base-white px-6 py-4 rounded-t-lg">
        <DialogTitle class="text-base-white text-lg">
          {{ t('views.direct-viewer.reset-modal.title') }}
        </DialogTitle>
        <DialogDescription class="sr-only">
          {{ t('views.direct-viewer.reset-modal.option.reset-desktop') }}
        </DialogDescription>
      </DialogHeader>

      <div class="flex items-center justify-between gap-4 px-6 py-6">
        <p class="flex-1 text-gray-warm-700">
          {{ t('views.direct-viewer.reset-modal.option.reset-desktop') }}
        </p>
        <Button
          hierarchy="destructive"
          size="sm"
          :disabled="reset.isPending.value"
          @click="handleReset"
        >
          {{ t('views.direct-viewer.reset-modal.confirmation.reset-desktop') }}
        </Button>
      </div>
    </DialogContent>
  </Dialog>
</template>
