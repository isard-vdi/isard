<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/icon'

interface Props {
  open?: boolean
  documentationUrl?: string
}

const props = withDefaults(defineProps<Props>(), { open: false, documentationUrl: '' })
const emit = defineEmits<{ close: [] }>()

const { t } = useI18n()
</script>

<template>
  <Dialog :open="props.open" @update:open="(v) => !v && emit('close')">
    <DialogContent
      class="bg-base-background shadow-md max-h-[90vh] flex flex-col p-0 w-[95vw] max-w-2xl"
    >
      <DialogHeader class="px-6 pt-6">
        <DialogTitle class="flex items-center gap-2 text-gray-warm-900 text-lg">
          <Icon name="star-01" stroke-color="warning-500" size="md" />
          {{ t('views.direct-viewer.help.rdp.local-client') }}
        </DialogTitle>
        <DialogDescription class="sr-only">
          {{ t('views.direct-viewer.help.rdp.rdp-help') }}
        </DialogDescription>
      </DialogHeader>

      <div class="px-6 pb-2 overflow-y-auto text-sm text-gray-warm-700">
        <hr class="my-3 border-gray-warm-300" />
        <p>
          <strong>{{ t('views.direct-viewer.help.rdp.included') }}</strong>
          {{ t('views.direct-viewer.help.rdp.client-required') }}
        </p>

        <div class="flex justify-center my-4">
          <Button
            v-if="props.documentationUrl"
            as="a"
            hierarchy="secondary-color"
            :href="props.documentationUrl"
            target="_blank"
            rel="noopener noreferrer"
          >
            {{ t('views.direct-viewer.help.rdp.download-install') }}
          </Button>
        </div>

        <p class="mt-2 mb-4">
          {{ t('views.direct-viewer.help.rdp.once-installed') }}
        </p>
      </div>

      <DialogFooter class="px-6 pb-4 sm:justify-center">
        <Button hierarchy="primary" @click="emit('close')">
          {{ t('views.direct-viewer.help.rdp.close-guide') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
